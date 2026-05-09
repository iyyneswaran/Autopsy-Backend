import { Router } from "express";
import { AuthController } from "./auth.controller";
import { authenticate } from "../middlewares/authenticate";
import { validate } from "../middlewares/validate";
import { authLimiter } from "../middlewares/rateLimiter";
import {
    signupSchema,
    loginSchema,
    changePasswordSchema,
} from "./auth.validators";

const router = Router();

// ─────────────────────────────────────────────
// Public routes
// ─────────────────────────────────────────────

router.post(
    "/signup",
    authLimiter,
    validate({ body: signupSchema }),
    AuthController.signup
);

router.post(
    "/login",
    authLimiter,
    validate({ body: loginSchema }),
    AuthController.login
);

router.post(
    "/refresh-token",
    AuthController.refreshToken
);

// ─────────────────────────────────────────────
// Protected routes
// ─────────────────────────────────────────────

router.post(
    "/logout",
    authenticate,
    AuthController.logout
);

router.get(
    "/me",
    authenticate,
    AuthController.getMe
);

router.post(
    "/change-password",
    authenticate,
    validate({ body: changePasswordSchema }),
    AuthController.changePassword
);

export default router;
