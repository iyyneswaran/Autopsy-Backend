import rateLimit from "express-rate-limit";
import { env } from "../config/env";

// ─────────────────────────────────────────────
// Global rate limiter
// ─────────────────────────────────────────────

export const globalLimiter = rateLimit({
    windowMs: env.RATE_LIMIT_WINDOW_MS,
    max: env.RATE_LIMIT_MAX_REQUESTS,
    standardHeaders: true,
    legacyHeaders: false,
    message: {
        success: false,
        message: "Too many requests, please try again later",
        error: { code: "RATE_LIMIT_EXCEEDED" },
    },
});

// ─────────────────────────────────────────────
// Strict limiter for auth endpoints
// ─────────────────────────────────────────────

export const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 10, // 10 attempts
    standardHeaders: true,
    legacyHeaders: false,
    message: {
        success: false,
        message: "Too many login attempts, please try again in 15 minutes",
        error: { code: "RATE_LIMIT_EXCEEDED" },
    },
});

// ─────────────────────────────────────────────
// Strict limiter for password reset
// ─────────────────────────────────────────────

export const passwordResetLimiter = rateLimit({
    windowMs: 60 * 60 * 1000, // 1 hour
    max: 3,
    standardHeaders: true,
    legacyHeaders: false,
    message: {
        success: false,
        message: "Too many password reset requests",
        error: { code: "RATE_LIMIT_EXCEEDED" },
    },
});
