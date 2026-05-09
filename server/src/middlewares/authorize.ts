import type { Request, Response, NextFunction } from "express";
import { ApiError } from "../utils/ApiError";
import type { Role } from "../constants";
import type { AuthenticatedRequest } from "../types";

// ─────────────────────────────────────────────
// Role-based access control middleware
// ─────────────────────────────────────────────

export function authorize(...allowedRoles: Role[]) {
    return (req: Request, _res: Response, next: NextFunction): void => {
        const user = (req as AuthenticatedRequest).user;

        if (!user) {
            next(ApiError.unauthorized());
            return;
        }

        if (!allowedRoles.includes(user.role)) {
            next(
                ApiError.forbidden(
                    `Role '${user.role}' does not have access to this resource`
                )
            );
            return;
        }

        next();
    };
}
