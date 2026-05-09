// ─────────────────────────────────────────────
// Application roles
// ─────────────────────────────────────────────

export const Roles = {
    ADMIN: "ADMIN",
    INVESTIGATOR: "INVESTIGATOR",
    FORENSIC_EXPERT: "FORENSIC_EXPERT",
} as const;

export type Role = (typeof Roles)[keyof typeof Roles];

export const ALL_ROLES: Role[] = Object.values(Roles);

// ─────────────────────────────────────────────
// Investigation statuses
// ─────────────────────────────────────────────

export const InvestigationStatus = {
    OPEN: "OPEN",
    IN_PROGRESS: "IN_PROGRESS",
    REVIEW: "REVIEW",
    CLOSED: "CLOSED",
    ARCHIVED: "ARCHIVED",
} as const;

export type InvestigationStatusType =
    (typeof InvestigationStatus)[keyof typeof InvestigationStatus];

// ─────────────────────────────────────────────
// Evidence types
// ─────────────────────────────────────────────

export const EvidenceType = {
    DOCUMENT: "DOCUMENT",
    IMAGE: "IMAGE",
    VIDEO: "VIDEO",
    AUDIO: "AUDIO",
    DIGITAL: "DIGITAL",
    PHYSICAL: "PHYSICAL",
    AUTOPSY_REPORT: "AUTOPSY_REPORT",
} as const;

export type EvidenceTypeValue =
    (typeof EvidenceType)[keyof typeof EvidenceType];

// ─────────────────────────────────────────────
// HTTP status codes
// ─────────────────────────────────────────────

export const HttpStatus = {
    OK: 200,
    CREATED: 201,
    NO_CONTENT: 204,
    BAD_REQUEST: 400,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    NOT_FOUND: 404,
    CONFLICT: 409,
    UNPROCESSABLE: 422,
    TOO_MANY_REQUESTS: 429,
    INTERNAL_SERVER: 500,
    SERVICE_UNAVAILABLE: 503,
} as const;

// ─────────────────────────────────────────────
// Error codes for frontend consumption
// ─────────────────────────────────────────────

export const ErrorCode = {
    VALIDATION_ERROR: "VALIDATION_ERROR",
    AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED",
    INVALID_CREDENTIALS: "INVALID_CREDENTIALS",
    TOKEN_EXPIRED: "TOKEN_EXPIRED",
    TOKEN_INVALID: "TOKEN_INVALID",
    ACCOUNT_LOCKED: "ACCOUNT_LOCKED",
    INSUFFICIENT_PERMISSIONS: "INSUFFICIENT_PERMISSIONS",
    RESOURCE_NOT_FOUND: "RESOURCE_NOT_FOUND",
    RESOURCE_CONFLICT: "RESOURCE_CONFLICT",
    RATE_LIMIT_EXCEEDED: "RATE_LIMIT_EXCEEDED",
    INTERNAL_ERROR: "INTERNAL_ERROR",
    FILE_TOO_LARGE: "FILE_TOO_LARGE",
    INVALID_FILE_TYPE: "INVALID_FILE_TYPE",
} as const;

export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];

// ─────────────────────────────────────────────
// Pagination defaults
// ─────────────────────────────────────────────

export const PAGINATION = {
    DEFAULT_PAGE: 1,
    DEFAULT_LIMIT: 20,
    MAX_LIMIT: 100,
} as const;

// ─────────────────────────────────────────────
// Password policy
// ─────────────────────────────────────────────

export const PASSWORD_POLICY = {
    MIN_LENGTH: 8,
    MAX_LENGTH: 128,
    REQUIRE_UPPERCASE: true,
    REQUIRE_LOWERCASE: true,
    REQUIRE_NUMBER: true,
    REQUIRE_SPECIAL: true,
} as const;
