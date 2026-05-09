import { Router } from "express";
import authRoutes from "../auth/auth.routes";
import usersRoutes from "../modules/users/users.routes";
import investigationsRoutes from "../modules/investigations/investigations.routes";
import evidenceRoutes from "../modules/evidence/evidence.routes";
import { ApiResponse } from "../utils/ApiResponse";
import type { Request, Response } from "express";

// ═══════════════════════════════════════════════
// API v1 Router
// ═══════════════════════════════════════════════

const v1Router = Router();

// ─── Health check ──────────────────────────────
v1Router.get("/health", (_req: Request, res: Response) => {
    ApiResponse.success(res, {
        status: "healthy",
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        memory: process.memoryUsage(),
    }, "Service is healthy");
});

// ─── Module routes ─────────────────────────────
v1Router.use("/auth", authRoutes);
v1Router.use("/users", usersRoutes);
v1Router.use("/investigations", investigationsRoutes);
v1Router.use("/evidence", evidenceRoutes);

export default v1Router;
