import { Router } from "express";
import { UsersController } from "./users.controller";
import { authenticate } from "../../middlewares/authenticate";
import { authorize } from "../../middlewares/authorize";

const router = Router();

// All user routes require authentication + ADMIN role
router.use(authenticate);
router.use(authorize("ADMIN"));

router.get("/", UsersController.list);
router.get("/:id", UsersController.getById);
router.patch("/:id/role", UsersController.updateRole);
router.patch("/:id/deactivate", UsersController.deactivate);
router.patch("/:id/reactivate", UsersController.reactivate);

export default router;
