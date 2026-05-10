import { Router } from "express";
import { InvestigationsController } from "./investigations.controller";
import { authenticate } from "../../middlewares/authenticate";
import { authorize } from "../../middlewares/authorize";
import { validate } from "../../middlewares/validate";
import {
    createInvestigationSchema,
    updateInvestigationSchema,
} from "./investigations.validators";

const router = Router();

router.use(authenticate);

router.post(
    "/",
    authorize("ADMIN", "INVESTIGATOR"),
    validate({ body: createInvestigationSchema }),
    InvestigationsController.create
);

router.get("/", InvestigationsController.list);

router.get("/:id", InvestigationsController.getById);

router.patch(
    "/:id",
    authorize("ADMIN", "INVESTIGATOR"),
    validate({ body: updateInvestigationSchema }),
    InvestigationsController.update
);

router.delete(
    "/:id",
    authorize("ADMIN", "INVESTIGATOR"),
    InvestigationsController.delete
);

export default router;
