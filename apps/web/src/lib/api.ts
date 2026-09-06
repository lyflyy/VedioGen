export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => null);
    throw new ApiError(problem?.detail ?? problem?.title ?? `请求失败 (${response.status})`, response.status, problem?.detail);
  }
  return response.json() as Promise<T>;
}

export function post<T>(path: string, body?: unknown) {
  return api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
}

export function put<T>(path: string, body: unknown) {
  return api<T>(path, { method: "PUT", body: JSON.stringify(body) });
}
