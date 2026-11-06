import { prisma } from '../../config/database';
import { ApiError } from '../../utils/ApiError';
import type { JwtPayload } from '../../types';
import { z } from 'zod/v4';

export function caseScope(user: JwtPayload) {
    return user.role === 'ADMIN' ? {} : { OR: [{ createdById: user.userId }, { assignedToId: user.userId }] };
}

export async function requireCase(user: JwtPayload, id: string) {
    if (!z.uuid().safeParse(id).success) throw ApiError.notFound('Investigation');
    const result = await prisma.investigation.findFirst({ where: { id, ...caseScope(user) } });
    if (!result) throw ApiError.notFound('Investigation');
    return result;
}
