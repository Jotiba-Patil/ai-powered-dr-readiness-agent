// Shared request plumbing for the typed clients: every failure becomes an ApiError.

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export function toApiError(body: unknown, status: number): ApiError {
  if (typeof body === "object" && body !== null && "error" in body && "code" in body) {
    const { error, code } = body as { error: unknown; code: unknown };
    if (typeof error === "string" && typeof code === "string") {
      return new ApiError(error, code, status);
    }
  }
  return new ApiError(`Request failed with status ${status}`, "HTTP_ERROR", status);
}

export async function call<T>(
  baseUrl: string,
  request: () => Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await request();
  } catch {
    const where = baseUrl ? ` at ${baseUrl}` : "";
    throw new ApiError(`Cannot reach the API${where}. Is it running?`, "NETWORK_ERROR", 0);
  }
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result.error, result.response.status);
  }
  return result.data;
}
