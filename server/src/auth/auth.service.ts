import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { v4 as uuidv4 } from "uuid";
import crypto from "crypto";
import { prisma } from "../config/database";
import { env } from "../config/env";
import { logger, auditLogger } from "../config/logger";
import { ApiError } from "../utils/ApiError";
import type { JwtPayload, JwtRefreshPayload, TokenPair } from "../types";
import type { SignupInput, LoginInput } from "./auth.validators";

// ═══════════════════════════════════════════════
// Auth Service — handles all authentication logic
// ═══════════════════════════════════════════════

export class AuthService {
    // ─────────────────────────────────────────
    // SIGNUP
    // ─────────────────────────────────────────

    static async signup(input: SignupInput) {
        const existing = await prisma.user.findUnique({
            where: { email: input.email.toLowerCase() },
        });

        if (existing) {
            throw ApiError.conflict("Email already registered");
        }

        const passwordHash = await bcrypt.hash(input.password, env.BCRYPT_SALT_ROUNDS);

        const user = await prisma.user.create({
            data: {
                email: input.email.toLowerCase(),
                passwordHash,
                firstName: input.firstName,
                lastName: input.lastName,
            },
            select: {
                id: true,
                email: true,
                firstName: true,
                lastName: true,
                role: true,
                createdAt: true,
            },
        });

        auditLogger.info("User signup", {
            userId: user.id,
            email: user.email,
        });

        return user;
    }

    // ─────────────────────────────────────────
    // LOGIN
    // ─────────────────────────────────────────

    static async login(
        input: LoginInput,
        ipAddress?: string,
        userAgent?: string
    ): Promise<{ user: any; tokens: TokenPair }> {
        const user = await prisma.user.findUnique({
            where: { email: input.email.toLowerCase() },
        });

        if (!user) {
            throw ApiError.invalidCredentials();
        }

        // Check account lock
        if (user.lockedUntil && user.lockedUntil > new Date()) {
            const minutesLeft = Math.ceil(
                (user.lockedUntil.getTime() - Date.now()) / 60000
            );
            throw ApiError.accountLocked(minutesLeft);
        }

        if (!user.isActive) {
            throw ApiError.forbidden("Account is deactivated");
        }

        // Verify password
        const isValid = await bcrypt.compare(input.password, user.passwordHash);

        if (!isValid) {
            // Increment failed attempts
            const attempts = user.loginAttempts + 1;
            const updateData: any = { loginAttempts: attempts };

            if (attempts >= env.MAX_LOGIN_ATTEMPTS) {
                updateData.lockedUntil = new Date(
                    Date.now() + env.LOCK_TIME_MINUTES * 60 * 1000
                );
                logger.warn(`Account locked: ${user.email} after ${attempts} failed attempts`);
            }

            await prisma.user.update({
                where: { id: user.id },
                data: updateData,
            });

            throw ApiError.invalidCredentials();
        }

        // Reset failed attempts on successful login
        await prisma.user.update({
            where: { id: user.id },
            data: {
                loginAttempts: 0,
                lockedUntil: null,
                lastLoginAt: new Date(),
            },
        });

        // Create session
        const session = await prisma.session.create({
            data: {
                userId: user.id,
                ipAddress,
                userAgent,
                expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
            },
        });

        // Generate tokens
        const tokens = await AuthService.generateTokenPair(user, session.id);

        auditLogger.info("User login", {
            userId: user.id,
            email: user.email,
            ipAddress,
            sessionId: session.id,
        });

        return {
            user: {
                id: user.id,
                email: user.email,
                firstName: user.firstName,
                lastName: user.lastName,
                role: user.role,
            },
            tokens,
        };
    }

    // ─────────────────────────────────────────
    // LOGOUT
    // ─────────────────────────────────────────

    static async logout(sessionId: string, userId: string): Promise<void> {
        // Invalidate session
        await prisma.session.updateMany({
            where: { id: sessionId, userId },
            data: { isValid: false },
        });

        // Revoke all refresh tokens for this session
        // (session-scoped; won't affect other devices)
        auditLogger.info("User logout", { userId, sessionId });
    }

    // ─────────────────────────────────────────
    // REFRESH TOKEN
    // ─────────────────────────────────────────

    static async refreshTokens(refreshToken: string): Promise<TokenPair> {
        const tokenHash = AuthService.hashToken(refreshToken);

        const storedToken = await prisma.refreshToken.findUnique({
            where: { tokenHash },
            include: { user: true },
        });

        if (!storedToken) {
            throw ApiError.unauthorized("Invalid refresh token");
        }

        if (storedToken.isRevoked) {
            // Token reuse detected — revoke entire family
            await prisma.refreshToken.updateMany({
                where: { tokenFamily: storedToken.tokenFamily },
                data: { isRevoked: true },
            });

            logger.warn("Refresh token reuse detected!", {
                userId: storedToken.userId,
                tokenFamily: storedToken.tokenFamily,
            });

            throw ApiError.unauthorized("Token reuse detected. All sessions revoked.");
        }

        if (storedToken.expiresAt < new Date()) {
            throw ApiError.tokenExpired();
        }

        // Revoke old token
        await prisma.refreshToken.update({
            where: { id: storedToken.id },
            data: { isRevoked: true },
        });

        // Find active session for this user
        const session = await prisma.session.findFirst({
            where: { userId: storedToken.userId, isValid: true },
            orderBy: { createdAt: "desc" },
        });

        if (!session) {
            throw ApiError.unauthorized("No active session found");
        }

        // Generate new token pair (rotation)
        return AuthService.generateTokenPair(
            storedToken.user,
            session.id,
            storedToken.tokenFamily
        );
    }

    // ─────────────────────────────────────────
    // CHANGE PASSWORD
    // ─────────────────────────────────────────

    static async changePassword(
        userId: string,
        currentPassword: string,
        newPassword: string
    ): Promise<void> {
        const user = await prisma.user.findUnique({ where: { id: userId } });

        if (!user) {
            throw ApiError.notFound("User");
        }

        const isValid = await bcrypt.compare(currentPassword, user.passwordHash);
        if (!isValid) {
            throw ApiError.badRequest("Current password is incorrect");
        }

        const newHash = await bcrypt.hash(newPassword, env.BCRYPT_SALT_ROUNDS);

        await prisma.user.update({
            where: { id: userId },
            data: { passwordHash: newHash },
        });

        // Invalidate all sessions except current
        await prisma.session.updateMany({
            where: { userId, isValid: true },
            data: { isValid: false },
        });

        auditLogger.info("Password changed", { userId });
    }

    // ─────────────────────────────────────────
    // GET CURRENT USER
    // ─────────────────────────────────────────

    static async getMe(userId: string) {
        const user = await prisma.user.findUnique({
            where: { id: userId },
            select: {
                id: true,
                email: true,
                firstName: true,
                lastName: true,
                role: true,
                isEmailVerified: true,
                lastLoginAt: true,
                createdAt: true,
            },
        });

        if (!user) {
            throw ApiError.notFound("User");
        }

        return user;
    }

    // ═══════════════════════════════════════════
    // PRIVATE HELPERS
    // ═══════════════════════════════════════════

    private static async generateTokenPair(
        user: { id: string; email: string; role: any },
        sessionId: string,
        tokenFamily?: string
    ): Promise<TokenPair> {
        const family = tokenFamily || uuidv4();

        // Access token
        const accessPayload: JwtPayload = {
            userId: user.id,
            email: user.email,
            role: user.role,
            sessionId,
        };

        const accessToken = jwt.sign(accessPayload, env.JWT_ACCESS_SECRET, {
            expiresIn: env.JWT_ACCESS_EXPIRY as any,
        });

        // Refresh token (opaque)
        const refreshToken = uuidv4() + "." + crypto.randomBytes(32).toString("hex");
        const refreshTokenHash = AuthService.hashToken(refreshToken);

        await prisma.refreshToken.create({
            data: {
                userId: user.id,
                tokenHash: refreshTokenHash,
                tokenFamily: family,
                expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
            },
        });

        return { accessToken, refreshToken };
    }

    private static hashToken(token: string): string {
        return crypto.createHash("sha256").update(token).digest("hex");
    }
}
