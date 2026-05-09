import type { Request, Response, NextFunction } from "express";
import { Prisma } from "@prisma/client";
import { ZodError } from "zod/v4";
import { ApiError } from "../utils/ApiError";
import { ApiResponse } from "../utils/ApiResponse";
import { logger } from "../config/logger";
import { isProd } from "../config/env";

// ─────────────────────────────────────────────
// Centralized error handler middleware
// ─────────────────────────────────────────────

export function errorHandler(
    err: Error,
    _req: Request,
    res: Response,
    _next: NextFunction
): void {
    // ─── Known operational errors ──────────────
    if (err instanceof ApiError) {
        ApiResponse.error(res, err.statusCode, err.message, err.code, err.details);
        return;
    }

    // ─── Zod validation errors ─────────────────
    if (err instanceof ZodError) {
        const details = err.issues.map((issue) => ({
            field: issue.path.join("."),
            message: issue.message,
        }));
        ApiResponse.error(res, 422, "Validation failed", "VALIDATION_ERROR", details);
        return;
    }

    // ─── Prisma errors ─────────────────────────
    if (err instanceof Prisma.PrismaClientKnownRequestError) {
        switch (err.code) {
            case "P2002": {
                const target = (err.meta?.target as string[])?.join(", ") || "field";
                ApiResponse.error(res, 409, `Duplicate value for ${target}`, "RESOURCE_CONFLICT");
                return;
            }
            case "P2025":
                ApiResponse.error(res, 404, "Record not found", "RESOURCE_NOT_FOUND");
                return;
            case "P2003":
                ApiResponse.error(res, 400, "Related record not found", "VALIDATION_ERROR");
                return;
            default:
                logger.error(`Prisma error ${err.code}:`, err.message);
        }
    }

    if (err instanceof Prisma.PrismaClientValidationError) {
        ApiResponse.error(res, 400, "Invalid data provided", "VALIDATION_ERROR");
        return;
    }

    // ─── JWT errors ────────────────────────────
    if (err.name === "JsonWebTokenError") {
        ApiResponse.error(res, 401, "Invalid token", "TOKEN_INVALID");
        return;
    }

    if (err.name === "TokenExpiredError") {
        ApiResponse.error(res, 401, "Token has expired", "TOKEN_EXPIRED");
        return;
    }

    // ─── Multer errors ─────────────────────────
    if (err.name === "MulterError") {
        ApiResponse.error(res, 400, err.message, "FILE_TOO_LARGE");
        return;
    }

    // ─── Unknown errors ────────────────────────
    logger.error("Unhandled error:", {
        message: err.message,
        stack: err.stack,
        name: err.name,
    });

    ApiResponse.error(
        res,
        500,
        isProd ? "Internal server error" : err.message,
        "INTERNAL_ERROR",
        isProd ? undefined : err.stack
    );
}
