import { Router } from 'express';
import axios from 'axios';
import { authenticate, validateSession } from '../../middlewares/authenticate';
import { env } from '../../config/env';
import { asyncHandler } from '../../utils/asyncHandler';

const router = Router();
router.use(authenticate, validateSession);
router.use(asyncHandler(async (req, res) => {
    const multipart = req.is('multipart/form-data');
    const upstream = await axios.request({
        url: `${env.FASTAPI_URL}/api/v1/intelligence${req.url}`,
        method: req.method,
        headers: { Authorization: req.headers.authorization,
            'Content-Type': req.headers['content-type'] || 'application/json' },
        data: ['GET', 'HEAD'].includes(req.method) ? undefined : multipart ? req : req.body,
        responseType: 'stream', validateStatus: () => true,
        maxBodyLength: Infinity, timeout: 120000,
    });
    res.status(upstream.status);
    for (const name of ['content-type', 'content-disposition', 'x-evidence-sha256']) {
        if (upstream.headers[name]) res.setHeader(name, upstream.headers[name]);
    }
    upstream.data.on('error', () => res.destroy());
    upstream.data.pipe(res);
}));
export default router;
