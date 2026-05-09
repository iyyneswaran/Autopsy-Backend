import dotenv from "dotenv";
import { z } from "zod/v4";

dotenv.config();

// ─────────────────────────────────────────────
// Validated environment schema
// ─────────────────────────────────────────────

const envSchema = z.object({
    NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
    PORT: z.coerce.number().default(5000),

    DATABASE_URL: z.string().min(1, "DATABASE_URL is required"),

    JWT_ACCESS_SECRET: z.string().min(32, "JWT_ACCESS_SECRET must be ≥32 chars"),
    JWT_REFRESH_SECRET: z.string().min(32, "JWT_REFRESH_SECRET must be ≥32 chars"),
    JWT_ACCESS_EXPIRY: z.string().default("15m"),
    JWT_REFRESH_EXPIRY: z.string().default("7d"),

    CORS_ORIGIN: z.string().default("http://localhost:5173"),
    FASTAPI_URL: z.string().default("http://127.0.0.1:8001"),

    RATE_LIMIT_WINDOW_MS: z.coerce.number().default(900_000),
    RATE_LIMIT_MAX_REQUESTS: z.coerce.number().default(100),

    LOG_LEVEL: z.string().default("debug"),
    BCRYPT_SALT_ROUNDS: z.coerce.number().default(12),

    MAX_LOGIN_ATTEMPTS: z.coerce.number().default(5),
    LOCK_TIME_MINUTES: z.coerce.number().default(30),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
    console.error("❌ Invalid environment variables:");
    console.error(JSON.stringify(parsed.error.format(), null, 2));
    process.exit(1);
}

export const env = parsed.data;

export const isProd = env.NODE_ENV === "production";
export const isDev = env.NODE_ENV === "development";
export const isTest = env.NODE_ENV === "test";
