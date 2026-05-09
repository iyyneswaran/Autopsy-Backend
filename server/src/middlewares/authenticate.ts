import type { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { env } from "../config/env";
import { prisma } from "../config/database";
import { ApiError } from "../utils/ApiError";
import type { JwtPayload, AuthenticatedRequest } from "../types";

// ─────────────────────────────────────────────
// JWT Authentication middleware
// ─────────────────────────────────────────────

export function authenticate(req: Request, _res: Response, next: NextFunction): void {
    try {
        const authHeader = req.headers.authorization;

        if (!authHeader?.startsWith("Bearer ")) {
            throw ApiError.unauthorized("Access token required");
        }

        const token = authHeader.split(" ")[1];

        if (!token) {
            throw ApiError.unauthorized("Access token required");
        }

        const payload = jwt.verify(token, env.JWT_ACCESS_SECRET) as JwtPayload;

        (req as AuthenticatedRequest).user = payload;

        next();
    } catch (err) {
        if (err instanceof ApiError) {
            next(err);
            return;
        }

        if (err instanceof jwt.TokenExpiredError) {
            next(ApiError.tokenExpired());
            return;
        }

        next(ApiError.unauthorized("Invalid access token"));
    }
}

// ─────────────────────────────────────────────
// Optional auth — attaches user if present
// ─────────────────────────────────────────────

export function optionalAuth(req: Request, _res: Response, next: NextFunction): void {
    try {
        const authHeader = req.headers.authorization;

        if (authHeader?.startsWith("Bearer ")) {
            const token = authHeader.split(" ")[1];
            if (token) {
                const payload = jwt.verify(token, env.JWT_ACCESS_SECRET) as JwtPayload;
                (req as AuthenticatedRequest).user = payload;
            }
        }
    } catch {
        // Silently continue without auth
    }
    next();
}

// ─────────────────────────────────────────────
// Session validation — ensures session is active
// ─────────────────────────────────────────────

export async function validateSession(
    req: Request,
    _res: Response,
    next: NextFunction
): Promise<void> {
    try {
        const user = (req as AuthenticatedRequest).user;

        if (!user?.sessionId) {
            throw ApiError.unauthorized("Invalid session");
        }

        const session = await prisma.session.findUnique({
            where: { id: user.sessionId },
        });

        if (!session || !session.isValid || session.expiresAt < new Date()) {
            throw ApiError.unauthorized("Session expired or invalidated");
        }

        next();
    } catch (err) {
        next(err);
    }
}
