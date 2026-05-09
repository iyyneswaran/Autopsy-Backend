import type { Request, Response, NextFunction } from "express";
import { v4 as uuidv4 } from "uuid";
import morgan from "morgan";
import { logger } from "../config/logger";

// ─────────────────────────────────────────────
// Request ID middleware
// ─────────────────────────────────────────────

export function requestId(req: Request, res: Response, next: NextFunction): void {
    const id = (req.headers["x-request-id"] as string) || uuidv4();
    req.headers["x-request-id"] = id;
    res.setHeader("X-Request-Id", id);
    next();
}

// ─────────────────────────────────────────────
// Morgan HTTP logger (streams to Winston)
// ─────────────────────────────────────────────

const morganStream = {
    write: (message: string) => {
        logger.http(message.trim());
    },
};

export const httpLogger = morgan(
    ":method :url :status :res[content-length] - :response-time ms",
    { stream: morganStream }
);

// ─────────────────────────────────────────────
// 404 handler
// ─────────────────────────────────────────────

export function notFoundHandler(req: Request, res: Response, _next: NextFunction): void {
    res.status(404).json({
        success: false,
        message: `Route ${req.method} ${req.originalUrl} not found`,
        error: { code: "RESOURCE_NOT_FOUND" },
    });
}
