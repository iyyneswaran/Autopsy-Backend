import { z } from "zod/v4";
import { PASSWORD_POLICY } from "../constants";

// ─────────────────────────────────────────────
// Password validation regex
// ─────────────────────────────────────────────

const passwordRegex = new RegExp(
    `^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[@$!%*?&])[A-Za-z\\d@$!%*?&]{${PASSWORD_POLICY.MIN_LENGTH},${PASSWORD_POLICY.MAX_LENGTH}}$`
);

// ─────────────────────────────────────────────
// Auth validation schemas
// ─────────────────────────────────────────────

export const signupSchema = z.object({
    email: z.email("Invalid email address"),
    password: z
        .string()
        .min(PASSWORD_POLICY.MIN_LENGTH, `Password must be at least ${PASSWORD_POLICY.MIN_LENGTH} characters`)
        .max(PASSWORD_POLICY.MAX_LENGTH)
        .regex(
            passwordRegex,
            "Password must contain uppercase, lowercase, number, and special character"
        ),
    firstName: z.string().min(1, "First name is required").max(100).trim(),
    lastName: z.string().min(1, "Last name is required").max(100).trim(),
});

export const loginSchema = z.object({
    email: z.email("Invalid email address"),
    password: z.string().min(1, "Password is required"),
});

export const refreshTokenSchema = z.object({
    refreshToken: z.string().min(1, "Refresh token is required"),
});

export const forgotPasswordSchema = z.object({
    email: z.email("Invalid email address"),
});

export const resetPasswordSchema = z.object({
    token: z.string().min(1, "Reset token is required"),
    password: z
        .string()
        .min(PASSWORD_POLICY.MIN_LENGTH)
        .max(PASSWORD_POLICY.MAX_LENGTH)
        .regex(
            passwordRegex,
            "Password must contain uppercase, lowercase, number, and special character"
        ),
});

export const changePasswordSchema = z.object({
    currentPassword: z.string().min(1, "Current password is required"),
    newPassword: z
        .string()
        .min(PASSWORD_POLICY.MIN_LENGTH)
        .max(PASSWORD_POLICY.MAX_LENGTH)
        .regex(
            passwordRegex,
            "Password must contain uppercase, lowercase, number, and special character"
        ),
});

// ─────────────────────────────────────────────
// Type exports
// ─────────────────────────────────────────────

export type SignupInput = z.infer<typeof signupSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type RefreshTokenInput = z.infer<typeof refreshTokenSchema>;
export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>;
export type ChangePasswordInput = z.infer<typeof changePasswordSchema>;
