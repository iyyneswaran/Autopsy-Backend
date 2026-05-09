import type { Request, Response } from "express";
import { prisma } from "../../config/database";
import { ApiResponse } from "../../utils/ApiResponse";
import { ApiError } from "../../utils/ApiError";
import { asyncHandler } from "../../utils/asyncHandler";
import { parsePagination } from "../../utils/pagination";
import { getParam } from "../../utils/params";
import type { AuthenticatedRequest } from "../../types";

// ═══════════════════════════════════════════════
// Evidence Controller
// ═══════════════════════════════════════════════

export class EvidenceController {
    // ─── CREATE (metadata only — file upload handled separately) ──
    static create = asyncHandler(async (req: Request, res: Response) => {
        const user = (req as AuthenticatedRequest).user;
        const { investigationId, type, fileName, filePath, fileHash, fileSize, mimeType, description, metadata } = req.body;

        // Verify investigation exists
        const investigation = await prisma.investigation.findUnique({
            where: { id: investigationId },
        });

        if (!investigation) throw ApiError.notFound("Investigation");

        const evidence = await prisma.evidence.create({
            data: {
                investigationId,
                type,
                fileName,
                filePath,
                fileHash,
                fileSize,
                mimeType,
                description,
                metadata,
                uploadedById: user.userId,
            },
            include: {
                uploadedBy: {
                    select: { id: true, firstName: true, lastName: true },
                },
            },
        });

        ApiResponse.created(res, evidence, "Evidence added");
    });

    // ─── LIST BY INVESTIGATION ─────────────────
    static listByInvestigation = asyncHandler(async (req: Request, res: Response) => {
        const { page, limit, skip, sortBy, sortOrder } = parsePagination(req);
        const investigationId = getParam(req, "investigationId");
        const type = req.query.type as string | undefined;

        const where: any = { investigationId };
        if (type) where.type = type;

        const [evidence, total] = await Promise.all([
            prisma.evidence.findMany({
                where,
                skip,
                take: limit,
                orderBy: { [sortBy]: sortOrder },
                include: {
                    uploadedBy: {
                        select: { id: true, firstName: true, lastName: true },
                    },
                },
            }),
            prisma.evidence.count({ where }),
        ]);

        ApiResponse.paginated(res, evidence, total, page, limit);
    });

    // ─── GET BY ID ─────────────────────────────
    static getById = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");

        const evidence = await prisma.evidence.findUnique({
            where: { id },
            include: {
                investigation: {
                    select: { id: true, caseNumber: true, title: true },
                },
                uploadedBy: {
                    select: { id: true, firstName: true, lastName: true, email: true },
                },
            },
        });

        if (!evidence) throw ApiError.notFound("Evidence");

        ApiResponse.success(res, evidence);
    });

    // ─── DELETE ────────────────────────────────
    static delete = asyncHandler(async (req: Request, res: Response) => {
        const id = getParam(req, "id");

        const existing = await prisma.evidence.findUnique({
            where: { id },
        });

        if (!existing) throw ApiError.notFound("Evidence");

        await prisma.evidence.delete({ where: { id } });

        ApiResponse.success(res, null, "Evidence deleted");
    });
}
