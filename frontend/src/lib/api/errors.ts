// ApiError and the error codes. Every action returns its result or throws an ApiError.

import { MODULE_NAMES, type Module } from "./types";

export const ERROR_STATUS = {
  UNAUTHENTICATED: 401,
  FORBIDDEN: 403,
  MODULE_NOT_LICENSED: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  VALIDATION: 422,
  EXPIRED: 410,
  TOO_MANY_TRIES: 429,
  INTERNAL: 500,
  // The server could not be reached (no answer at all).
  NETWORK: 0,
} as const;

export const NETWORK_MESSAGE = "Cannot reach the server. Please try again.";

export type ErrorCode = keyof typeof ERROR_STATUS;

export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  // For VALIDATION: the field the message is about.
  readonly field?: string;

  constructor(code: ErrorCode, message: string, field?: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status ?? ERROR_STATUS[code];
    this.field = field;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function unauthenticated(message = "Please sign in."): ApiError {
  return new ApiError("UNAUTHENTICATED", message);
}

export function forbidden(message = "You do not have access to this."): ApiError {
  return new ApiError("FORBIDDEN", message);
}

export function moduleNotLicensed(module: Module): ApiError {
  return new ApiError("MODULE_NOT_LICENSED", "The " + MODULE_NAMES[module] + " module is not licensed for this installation.");
}

export function notFound(what: string): ApiError {
  return new ApiError("NOT_FOUND", what + " was not found.");
}

export function conflict(message: string): ApiError {
  return new ApiError("CONFLICT", message);
}

// The message names the field, e.g. validation("email", "Please enter a valid email.").
export function validation(field: string, message: string): ApiError {
  return new ApiError("VALIDATION", message, field);
}

export function expired(message: string): ApiError {
  return new ApiError("EXPIRED", message);
}

export function tooManyTries(message: string): ApiError {
  return new ApiError("TOO_MANY_TRIES", message);
}
