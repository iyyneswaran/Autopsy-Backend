import type { Request, Response } from "express";
import { prisma } from "../../config/database";
import { ApiResponse } from "../../utils/ApiResponse";
import { ApiError } from "../../utils/ApiError";
import { asyncHandler } from "../../utils/asyncHandler";
import { parsePagination } from "../../utils/pagination";
import { getParam } from "../../utils/params";
import type { AuthenticatedRequest } from "../../types";

// ═══════════════════════════════════════════════
// Users Controller (Admin-only)
// ═══════════════════════════════════════════════

export class UsersController {
    // ─── LIST ALL USERS ────────────────────────
    static list = asyncHandler(async (req: Request, res: Response) => {
        const { page, limit, skip, sortBy, sortOrder, search } = parsePagination(req);

        const where = search
            ? {
                  OR: [
                      { firstName: { contains: search, mode: "insensitive" as const } },
                      { lastName: { contains: search, mode: "insensitive" as const } },
                      { email: { contains: search, mode: "insensitive" as const } },
                  ],
              }
            : {};

        const [users, total] = await Promise.all([
            prisma.user.findMany({
                where,
                skip,
                take: limit,
                orderBy: { [sortBy]: sortOrder },
                select: {
                    id: true,
                    email: true,
                    firstName: true,
                    lastName: true,
                    role: true,
                    isActive: true,
                    isEmailVerified: true,
                    lastLoginAt: true,
                    createdAt: true,
                },
            }),
            prisma.user.count({ where }),
        ]);

        ApiResponse.paginated(res, users, total, page, limit);
    });

    // ─── GET SINGLE USER ───────────────────────
    static getById = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");

        const user = await prisma.user.findUnique({
            where: { id },
            select: {
                id: true,
                email: true,
                firstName: true,
                lastName: true,
                role: true,
                isActive: true,
                isEmailVerified: true,
                lastLoginAt: true,
                createdAt: true,
                _count: {
                    select: {
                        investigations: true,
                        evidence: true,
                    },
                },
            },
        });

        if (!user) throw ApiError.notFound("User");

        ApiResponse.success(res, user);
    });

    // ─── UPDATE USER ROLE ──────────────────────
    static updateRole = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");
        const { role } = req.body;

        const user = await prisma.user.update({
            where: { id },
            data: { role },
            select: {
                id: true,
                email: true,
                firstName: true,
                lastName: true,
                role: true,
            },
        });

        ApiResponse.success(res, user, "Role updated");
    });

    // ─── DEACTIVATE USER ───────────────────────
    static deactivate = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");
        const currentUser = (req as AuthenticatedRequest).user;

        if (currentUser.userId === id) {
            throw ApiError.badRequest("Cannot deactivate your own account");
        }

        await prisma.user.update({
            where: { id },
            data: { isActive: false },
        });

        // Invalidate all sessions
        await prisma.session.updateMany({
            where: { userId: id },
            data: { isValid: false },
        });

        ApiResponse.success(res, null, "User deactivated");
    });

    // ─── REACTIVATE USER ───────────────────────
    static reactivate = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");

        await prisma.user.update({
            where: { id },
            data: { isActive: true, loginAttempts: 0, lockedUntil: null },
        });

        ApiResponse.success(res, null, "User reactivated");
    });
}
