import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import { Pool } from "pg";
import { logger } from "./logger";

// ─────────────────────────────────────────────
// Prisma 7 requires a driver adapter.
// We use @prisma/adapter-pg with the pg Pool.
// ─────────────────────────────────────────────

const globalForPrisma = globalThis as unknown as {
    prisma: PrismaClient | undefined;
};

function createPrismaClient(): PrismaClient {
    const pool = new Pool({
        connectionString: process.env.DATABASE_URL,
    });

    const adapter = new PrismaPg(pool);

    return new PrismaClient({ adapter } as any);
}

export const prisma = globalForPrisma.prisma ?? createPrismaClient();

// Log slow queries in development
prisma.$on("query" as never, (e: any) => {
    if (e.duration > 500) {
        logger.warn(`Slow query (${e.duration}ms): ${e.query}`);
    }
});

prisma.$on("error" as never, (e: any) => {
    logger.error("Prisma error:", e);
});

if (process.env.NODE_ENV !== "production") {
    globalForPrisma.prisma = prisma;
}

export default prisma;
