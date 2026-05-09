import type { Request } from "express";

/**
 * Safely extract a single string parameter from Express 5 params.
 * Express 5 types params as string | string[]; this ensures a string.
 */
export function getParam(req: Request, name: string): string {
    const value = req.params[name];
    return Array.isArray(value) ? value[0] : value;
}
