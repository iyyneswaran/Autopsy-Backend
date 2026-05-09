import type { Request, Response, NextFunction } from "express";
import { ZodSchema } from "zod/v4";
import { ApiError } from "../utils/ApiError";

// ─────────────────────────────────────────────
// Zod validation middleware
// ─────────────────────────────────────────────

interface ValidationSchemas {
    body?: ZodSchema;
    query?: ZodSchema;
    params?: ZodSchema;
}

export function validate(schemas: ValidationSchemas) {
    return (req: Request, _res: Response, next: NextFunction): void => {
        try {
            if (schemas.body) {
                req.body = schemas.body.parse(req.body);
            }
            if (schemas.query) {
                req.query = schemas.query.parse(req.query) as any;
            }
            if (schemas.params) {
                req.params = schemas.params.parse(req.params) as any;
            }
            next();
        } catch (err) {
            next(err); // Caught by errorHandler as ZodError
        }
    };
}
