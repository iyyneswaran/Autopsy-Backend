import type { Request, Response } from "express";
import { AuthService } from "./auth.service";
import { ApiResponse } from "../utils/ApiResponse";
import { ApiError } from "../utils/ApiError";
import { asyncHandler } from "../utils/asyncHandler";
import type { AuthenticatedRequest } from "../types";
import { env } from "../config/env";

// ═══════════════════════════════════════════════
// Auth Controller
// ═══════════════════════════════════════════════

export class AuthController {
    // ─── SIGNUP ────────────────────────────────
    static signup = asyncHandler(async (req: Request, res: Response) => {
        const user = await AuthService.signup(req.body);
        ApiResponse.created(res, user, "Account created successfully");
    });

    // ─── LOGIN ─────────────────────────────────
    static login = asyncHandler(async (req: Request, res: Response) => {
        const ipAddress = req.ip || req.socket.remoteAddress;
        const userAgent = req.headers["user-agent"];

        const { user, tokens } = await AuthService.login(req.body, ipAddress, userAgent);

        // Set refresh token in HTTP-only cookie
        res.cookie("refreshToken", tokens.refreshToken, {
            httpOnly: true,
            secure: env.NODE_ENV === "production",
            sameSite: "strict",
            maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days
            path: "/api/v1/auth",
        });

        ApiResponse.success(res, {
            user,
            accessToken: tokens.accessToken,
        }, "Login successful");
    });

    // ─── LOGOUT ────────────────────────────────
    static logout = asyncHandler(async (req: Request, res: Response) => {
        const user = (req as AuthenticatedRequest).user;
        await AuthService.logout(user.sessionId, user.userId);

        res.clearCookie("refreshToken", {
            httpOnly: true,
            secure: env.NODE_ENV === "production",
            sameSite: "strict",
            path: "/api/v1/auth",
        });

        ApiResponse.success(res, null, "Logged out successfully");
    });

    // ─── REFRESH TOKEN ─────────────────────────
    static refreshToken = asyncHandler(async (req: Request, res: Response) => {
        const token = req.cookies?.refreshToken || req.body.refreshToken;

        if (!token) {
            throw ApiError.unauthorized("Refresh token required");
        }

        const tokens = await AuthService.refreshTokens(token);

        // Rotate cookie
        res.cookie("refreshToken", tokens.refreshToken, {
            httpOnly: true,
            secure: env.NODE_ENV === "production",
            sameSite: "strict",
            maxAge: 7 * 24 * 60 * 60 * 1000,
            path: "/api/v1/auth",
        });

        ApiResponse.success(res, {
            accessToken: tokens.accessToken,
        }, "Token refreshed");
    });

    // ─── CHANGE PASSWORD ───────────────────────
    static changePassword = asyncHandler(async (req: Request, res: Response) => {
        const user = (req as AuthenticatedRequest).user;
        await AuthService.changePassword(
            user.userId,
            req.body.currentPassword,
            req.body.newPassword
        );

        ApiResponse.success(res, null, "Password changed successfully");
    });

    // ─── GET ME ────────────────────────────────
    static getMe = asyncHandler(async (req: Request, res: Response) => {
        const user = (req as AuthenticatedRequest).user;
        const profile = await AuthService.getMe(user.userId);
        ApiResponse.success(res, profile);
    });
}
