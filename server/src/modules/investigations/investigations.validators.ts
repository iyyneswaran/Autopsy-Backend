import { z } from "zod/v4";

export const createInvestigationSchema = z.object({
    title: z.string().min(3, "Title must be at least 3 characters").max(200),
    description: z.string().min(10, "Description must be at least 10 characters").max(5000),
    priority: z.coerce.number().int().min(0).max(5).optional(),
    assignedToId: z.string().uuid().optional(),
});

export const updateInvestigationSchema = z.object({
    title: z.string().min(3).max(200).optional(),
    description: z.string().min(10).max(5000).optional(),
    status: z.enum(["OPEN", "IN_PROGRESS", "REVIEW", "CLOSED", "ARCHIVED"]).optional(),
    priority: z.coerce.number().int().min(0).max(5).optional(),
    assignedToId: z.string().uuid().nullable().optional(),
});
