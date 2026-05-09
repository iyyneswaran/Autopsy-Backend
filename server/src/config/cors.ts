import type { CorsOptions } from "cors";
import { env } from "./env";

export const corsOptions: CorsOptions = {
    origin: (origin, callback) => {
        const allowedOrigins = env.CORS_ORIGIN.split(",").map((o) => o.trim());

        // Allow requests with no origin (mobile apps, curl, etc.)
        if (!origin || allowedOrigins.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error(`Origin ${origin} not allowed by CORS`));
        }
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowedHeaders: [
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Origin",
    ],
    exposedHeaders: ["X-Total-Count", "X-Request-Id"],
    maxAge: 86400, // 24 hours preflight cache
};
