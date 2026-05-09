import { Router } from "express";
import { EvidenceController } from "./evidence.controller";
import { authenticate } from "../../middlewares/authenticate";
import { authorize } from "../../middlewares/authorize";

const router = Router();

router.use(authenticate);

router.post(
    "/",
    authorize("ADMIN", "INVESTIGATOR", "FORENSIC_EXPERT"),
    EvidenceController.create
);

router.get(
    "/investigation/:investigationId",
    EvidenceController.listByInvestigation
);

router.get("/:id", EvidenceController.getById);

router.delete(
    "/:id",
    authorize("ADMIN"),
    EvidenceController.delete
);

export default router;
