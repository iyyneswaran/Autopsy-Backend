import { env } from "./config/env";
import { logger } from "./config/logger";
import { prisma } from "./config/database";
import app from "./app";

// ═══════════════════════════════════════════════
// Server bootstrap with graceful shutdown
// ═══════════════════════════════════════════════

const server = app.listen(env.PORT, () => {
    logger.info(`🚀 Atopsy server running on port ${env.PORT}`);
    logger.info(`📋 Environment: ${env.NODE_ENV}`);
    logger.info(`🔗 API: http://localhost:${env.PORT}/api/v1`);
    logger.info(`❤️  Health: http://localhost:${env.PORT}/api/v1/health`);
});

// ─────────────────────────────────────────────
// Graceful shutdown
// ─────────────────────────────────────────────

const gracefulShutdown = async (signal: string) => {
    logger.info(`${signal} received. Starting graceful shutdown...`);

    server.close(async () => {
        logger.info("HTTP server closed");

        try {
            await prisma.$disconnect();
            logger.info("Database disconnected");
        } catch (err) {
            logger.error("Error disconnecting database:", err);
        }

        process.exit(0);
    });

    // Force shutdown after 30 seconds
    setTimeout(() => {
        logger.error("Forced shutdown — could not close connections in time");
        process.exit(1);
    }, 30_000);
};

process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
process.on("SIGINT", () => gracefulShutdown("SIGINT"));

// ─────────────────────────────────────────────
// Unhandled errors
// ─────────────────────────────────────────────

process.on("unhandledRejection", (reason: unknown) => {
    logger.error("Unhandled rejection:", reason);
});

process.on("uncaughtException", (error: Error) => {
    logger.error("Uncaught exception:", error);
    process.exit(1);
});

export default server;