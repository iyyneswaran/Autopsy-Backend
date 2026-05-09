import winston from "winston";
import DailyRotateFile from "winston-daily-rotate-file";
import path from "path";
import { env, isProd } from "./env";

const logDir = path.join(__dirname, "..", "logs");

// ─────────────────────────────────────────────
// Custom log format
// ─────────────────────────────────────────────

const logFormat = winston.format.combine(
    winston.format.timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
    winston.format.errors({ stack: true }),
    winston.format.json()
);

const consoleFormat = winston.format.combine(
    winston.format.colorize(),
    winston.format.timestamp({ format: "HH:mm:ss" }),
    winston.format.printf(({ timestamp, level, message, ...meta }) => {
        const metaStr = Object.keys(meta).length ? JSON.stringify(meta) : "";
        return `${timestamp} ${level}: ${message} ${metaStr}`;
    })
);

// ─────────────────────────────────────────────
// Transport configuration
// ─────────────────────────────────────────────

const transports: winston.transport[] = [
    new winston.transports.Console({
        format: consoleFormat,
        silent: false,
    }),
];

// File transports for non-test environments
if (env.NODE_ENV !== "test") {
    transports.push(
        new DailyRotateFile({
            dirname: logDir,
            filename: "app-%DATE%.log",
            datePattern: "YYYY-MM-DD",
            maxSize: "20m",
            maxFiles: "14d",
            format: logFormat,
        }),
        new DailyRotateFile({
            dirname: logDir,
            filename: "error-%DATE%.log",
            datePattern: "YYYY-MM-DD",
            maxSize: "20m",
            maxFiles: "30d",
            level: "error",
            format: logFormat,
        })
    );
}

// ─────────────────────────────────────────────
// Logger instance
// ─────────────────────────────────────────────

export const logger = winston.createLogger({
    level: isProd ? "info" : env.LOG_LEVEL,
    defaultMeta: { service: "atopsy-server" },
    transports,
    exitOnError: false,
});

// ─────────────────────────────────────────────
// Audit logger for security events
// ─────────────────────────────────────────────

export const auditLogger = winston.createLogger({
    level: "info",
    defaultMeta: { service: "atopsy-audit" },
    transports: [
        new DailyRotateFile({
            dirname: logDir,
            filename: "audit-%DATE%.log",
            datePattern: "YYYY-MM-DD",
            maxSize: "50m",
            maxFiles: "90d",
            format: logFormat,
        }),
    ],
});
