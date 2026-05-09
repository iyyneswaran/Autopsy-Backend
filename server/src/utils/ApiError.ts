import { ErrorCodeValue, HttpStatus } from "../constants";

// ─────────────────────────────────────────────
// Custom API Error class
// ─────────────────────────────────────────────

export class ApiError extends Error {
    public readonly statusCode: number;
    public readonly code: ErrorCodeValue;
    public readonly isOperational: boolean;
    public readonly details?: unknown;

    constructor(
        statusCode: number,
        message: string,
        code: ErrorCodeValue,
        details?: unknown,
        isOperational = true
    ) {
        super(message);
        this.statusCode = statusCode;
        this.code = code;
        this.isOperational = isOperational;
        this.details = details;

        Object.setPrototypeOf(this, ApiError.prototype);
        Error.captureStackTrace(this, this.constructor);
    }

    // ─── Factory methods ───────────────────────

    static badRequest(message: string, details?: unknown) {
        return new ApiError(HttpStatus.BAD_REQUEST, message, "VALIDATION_ERROR", details);
    }

    static unauthorized(message = "Authentication required") {
        return new ApiError(HttpStatus.UNAUTHORIZED, message, "AUTHENTICATION_REQUIRED");
    }

    static forbidden(message = "Insufficient permissions") {
        return new ApiError(HttpStatus.FORBIDDEN, message, "INSUFFICIENT_PERMISSIONS");
    }

    static notFound(resource = "Resource") {
        return new ApiError(HttpStatus.NOT_FOUND, `${resource} not found`, "RESOURCE_NOT_FOUND");
    }

    static conflict(message: string) {
        return new ApiError(HttpStatus.CONFLICT, message, "RESOURCE_CONFLICT");
    }

    static tooManyRequests(message = "Too many requests") {
        return new ApiError(HttpStatus.TOO_MANY_REQUESTS, message, "RATE_LIMIT_EXCEEDED");
    }

    static internal(message = "Internal server error") {
        return new ApiError(HttpStatus.INTERNAL_SERVER, message, "INTERNAL_ERROR", undefined, false);
    }

    static invalidCredentials() {
        return new ApiError(HttpStatus.UNAUTHORIZED, "Invalid email or password", "INVALID_CREDENTIALS");
    }

    static tokenExpired() {
        return new ApiError(HttpStatus.UNAUTHORIZED, "Token has expired", "TOKEN_EXPIRED");
    }

    static accountLocked(minutes: number) {
        return new ApiError(
            HttpStatus.FORBIDDEN,
            `Account locked. Try again in ${minutes} minutes`,
            "ACCOUNT_LOCKED"
        );
    }
}
