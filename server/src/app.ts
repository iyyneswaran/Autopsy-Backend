import express from "express";
import cors from "cors";
import helmet from "helmet";
import compression from "compression";
import cookieParser from "cookie-parser";

import { corsOptions } from "./config/cors";
import { globalLimiter } from "./middlewares/rateLimiter";
import { requestId, httpLogger, notFoundHandler } from "./middlewares/requestLogger";
import { errorHandler } from "./middlewares/errorHandler";
import v1Router from "./routes/v1";

// ═══════════════════════════════════════════════
// Express Application
// ═══════════════════════════════════════════════

const app = express();

// ─────────────────────────────────────────────
// Security-first middleware ordering
// ─────────────────────────────────────────────

// 1. Request ID tracking
app.use(requestId);

// 2. Security headers
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "'unsafe-inline'"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["'self'", "data:", "https:"],
        },
    },
    crossOriginEmbedderPolicy: false,
}));

// 3. CORS
app.use(cors(corsOptions));

// 4. Rate limiting
app.use(globalLimiter);

// 5. Body parsing with size limits
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ extended: true, limit: "10mb" }));

// 6. Cookie parser
app.use(cookieParser());

// 7. Compression
app.use(compression());

// 8. HTTP request logging
app.use(httpLogger);

// ─────────────────────────────────────────────
// Trust proxy (for rate limiter behind nginx)
// ─────────────────────────────────────────────
app.set("trust proxy", 1);

// ─────────────────────────────────────────────
// Root endpoint
// ─────────────────────────────────────────────

app.get("/", (_req, res) => {
    res.json({
        success: true,
        message: "Atopsy Backend API",
        version: "1.0.0",
        docs: "/api/v1/health",
    });
});

// ─────────────────────────────────────────────
// API routes
// ─────────────────────────────────────────────

app.use("/api/v1", v1Router);

// ─────────────────────────────────────────────
// 404 + Error handling (must be last)
// ─────────────────────────────────────────────

app.use(notFoundHandler);
app.use(errorHandler);

export default app;