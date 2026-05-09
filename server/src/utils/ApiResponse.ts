import type { Response } from "express";
import type { ApiResponseShape } from "../types";

// ─────────────────────────────────────────────
// Standardized API response formatter
// ─────────────────────────────────────────────

export class ApiResponse {
    static success<T>(
        res: Response,
        data: T,
        message = "Success",
        statusCode = 200,
        meta?: Record<string, unknown>
    ): Response {
        const response: ApiResponseShape<T> = {
            success: true,
            message,
            data,
        };
        if (meta) response.meta = meta;
        return res.status(statusCode).json(response);
    }

    static created<T>(res: Response, data: T, message = "Created successfully"): Response {
        return ApiResponse.success(res, data, message, 201);
    }

    static noContent(res: Response): Response {
        return res.status(204).send();
    }

    static paginated<T>(
        res: Response,
        data: T[],
        total: number,
        page: number,
        limit: number,
        message = "Success"
    ): Response {
        const totalPages = Math.ceil(total / limit);
        return ApiResponse.success(res, data, message, 200, {
            total,
            page,
            limit,
            totalPages,
            hasNext: page < totalPages,
            hasPrev: page > 1,
        });
    }

    static error(
        res: Response,
        statusCode: number,
        message: string,
        code: string,
        details?: unknown
    ): Response {
        const response: ApiResponseShape = {
            success: false,
            message,
            error: { code, details },
        };
        return res.status(statusCode).json(response);
    }
}
