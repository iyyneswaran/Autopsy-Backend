import { caseScope, requireCase } from "./caseAccess";
import type { Request, Response } from "express";
import { prisma } from "../../config/database";
import { ApiResponse } from "../../utils/ApiResponse";
import { ApiError } from "../../utils/ApiError";
import { asyncHandler } from "../../utils/asyncHandler";
import { parsePagination } from "../../utils/pagination";
import { getParam } from "../../utils/params";
import type { AuthenticatedRequest } from "../../types";
import { v4 as uuidv4 } from "uuid";

// ═══════════════════════════════════════════════
// Investigations Controller
// ═══════════════════════════════════════════════

export class InvestigationsController {
    // ─── CREATE ────────────────────────────────
    static create = asyncHandler(async (req: Request, res: Response) => {
        const user = (req as AuthenticatedRequest).user;
        const { title, description, priority, assignedToId } = req.body;

        const caseNumber = `CASE-${Date.now()}-${uuidv4().slice(0, 4).toUpperCase()}`;

        const investigation = await prisma.investigation.create({
            data: {
                caseNumber,
                title,
                description,
                priority: priority || 0,
                createdById: user.userId,
                assignedToId,
            },
            include: {
                createdBy: {
                    select: { id: true, firstName: true, lastName: true, email: true },
                },
                assignedTo: {
                    select: { id: true, firstName: true, lastName: true, email: true },
                },
            },
        });

        await prisma.auditLog.create({data: {userId: user.userId, action: "CASE_CREATED", entity: "Investigation", entityId: investigation.id}});
        ApiResponse.created(res, investigation, "Investigation created");
    });

    // ─── LIST ──────────────────────────────────
    static list = asyncHandler(async (req: Request, res: Response) => {
        const { page, limit, skip, sortBy, sortOrder, search } = parsePagination(req);
        const status = req.query.status as string | undefined;

        const where: any = { AND: [caseScope((req as AuthenticatedRequest).user)] };

        if (search) {
            where.OR = [
                { title: { contains: search, mode: "insensitive" } },
                { caseNumber: { contains: search, mode: "insensitive" } },
                { description: { contains: search, mode: "insensitive" } },
            ];
        }

        if (status) {
            where.status = status;
        }

        const [investigations, total] = await Promise.all([
            prisma.investigation.findMany({
                where,
                skip,
                take: limit,
                orderBy: { [sortBy]: sortOrder },
                include: {
                    createdBy: {
                        select: { id: true, firstName: true, lastName: true },
                    },
                    assignedTo: {
                        select: { id: true, firstName: true, lastName: true },
                    },
                    _count: { select: { evidence: true, autopsyReports: true } },
                },
            }),
            prisma.investigation.count({ where }),
        ]);

        ApiResponse.paginated(res, investigations, total, page, limit);
    });

    // ─── GET BY ID ─────────────────────────────
    static getById = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");
        await requireCase((req as AuthenticatedRequest).user, id);

        const investigation = await prisma.investigation.findUnique({
            where: { id },
            include: {
                createdBy: {
                    select: { id: true, firstName: true, lastName: true, email: true },
                },
                assignedTo: {
                    select: { id: true, firstName: true, lastName: true, email: true },
                },
                evidence: {
                    select: {
                        id: true,
                        type: true,
                        fileName: true,
                        fileSize: true,
                        createdAt: true,
                    },
                },
                autopsyReports: {
                    select: {
                        id: true,
                        subjectName: true,
                        causeOfDeath: true,
                        createdAt: true,
                    },
                },
            },
        });

        if (!investigation) throw ApiError.notFound("Investigation");

        ApiResponse.success(res, investigation);
    });

    // ─── UPDATE ────────────────────────────────
    static update = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");
        await requireCase((req as AuthenticatedRequest).user, id);
        const { title, description, status, priority, assignedToId } = req.body;

        const existing = await prisma.investigation.findUnique({
            where: { id },
        });

        if (!existing) throw ApiError.notFound("Investigation");

        const investigation = await prisma.investigation.update({
            where: { id },
            data: {
                ...(title && { title }),
                ...(description && { description }),
                ...(status && { status }),
                ...(priority !== undefined && { priority }),
                ...(assignedToId !== undefined && { assignedToId }),
                ...(status === "CLOSED" && { closedAt: new Date() }),
            },
            include: {
                createdBy: {
                    select: { id: true, firstName: true, lastName: true },
                },
                assignedTo: {
                    select: { id: true, firstName: true, lastName: true },
                },
            },
        });

        await prisma.auditLog.create({data: {userId: (req as AuthenticatedRequest).user.userId, action: "CASE_UPDATED", entity: "Investigation", entityId: id, metadata: req.body}});
        ApiResponse.success(res, investigation, "Investigation updated");
    });

    // ─── DELETE ────────────────────────────────
    static delete = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");
        await requireCase((req as AuthenticatedRequest).user, id);

        const existing = await prisma.investigation.findUnique({
            where: { id },
        });

        if (!existing) throw ApiError.notFound("Investigation");

        await prisma.investigation.update({ where: { id }, data: { status: "ARCHIVED" } });

        ApiResponse.success(res, null, "Investigation archived; original evidence preserved");
    });
}
