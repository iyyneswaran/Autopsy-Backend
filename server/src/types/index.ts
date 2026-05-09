import type { Request } from "express";
import type { Role } from "../constants";

// ─────────────────────────────────────────────
// JWT payload types
// ─────────────────────────────────────────────

export interface JwtPayload {
    userId: string;
    email: string;
    role: Role;
    sessionId: string;
}

export interface JwtRefreshPayload {
    userId: string;
    sessionId: string;
    tokenFamily: string;
}

// ─────────────────────────────────────────────
// Authenticated request
// ─────────────────────────────────────────────

export interface AuthenticatedRequest extends Request {
    user: JwtPayload;
}

// ─────────────────────────────────────────────
// Pagination
// ─────────────────────────────────────────────

export interface PaginationQuery {
    page?: number;
    limit?: number;
    sortBy?: string;
    sortOrder?: "asc" | "desc";
    search?: string;
}

export interface PaginatedResult<T> {
    data: T[];
    meta: {
        total: number;
        page: number;
        limit: number;
        totalPages: number;
        hasNext: boolean;
        hasPrev: boolean;
    };
}

// ─────────────────────────────────────────────
// API Response
// ─────────────────────────────────────────────

export interface ApiResponseShape<T = unknown> {
    success: boolean;
    message: string;
    data?: T;
    error?: {
        code: string;
        details?: unknown;
    };
    meta?: Record<string, unknown>;
}

// ─────────────────────────────────────────────
// Token pair returned on login/refresh
// ─────────────────────────────────────────────

export interface TokenPair {
    accessToken: string;
    refreshToken: string;
}
