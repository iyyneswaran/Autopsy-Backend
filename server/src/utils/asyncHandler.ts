import type { Request, Response, NextFunction } from "express";

// ─────────────────────────────────────────────
// Async handler to catch errors in route handlers
// ─────────────────────────────────────────────

type AsyncHandler = (
    req: Request,
    res: Response,
    next: NextFunction
) => Promise<any>;

export const asyncHandler = (fn: AsyncHandler) => {
    return (req: Request, res: Response, next: NextFunction) => {
        Promise.resolve(fn(req, res, next)).catch(next);
    };
};
