import type { Request } from "express";
import { PAGINATION } from "../constants";

// ─────────────────────────────────────────────
// Pagination utility
// ─────────────────────────────────────────────

export interface PaginationOptions {
    page: number;
    limit: number;
    skip: number;
    sortBy: string;
    sortOrder: "asc" | "desc";
    search?: string;
}

export function parsePagination(req: Request, defaultSort = "createdAt"): PaginationOptions {
    const page = Math.max(1, parseInt(req.query.page as string) || PAGINATION.DEFAULT_PAGE);
    const limit = Math.min(
        PAGINATION.MAX_LIMIT,
        Math.max(1, parseInt(req.query.limit as string) || PAGINATION.DEFAULT_LIMIT)
    );
    const skip = (page - 1) * limit;
    const sortBy = (req.query.sortBy as string) || defaultSort;
    const sortOrder = (req.query.sortOrder as string) === "asc" ? "asc" : "desc";
    const search = req.query.search as string | undefined;

    return { page, limit, skip, sortBy, sortOrder, search };
}
