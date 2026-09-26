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
  const readOnly = !init?.method || init.method === "GET";
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    signal: init?.signal ?? (readOnly ? AbortSignal.timeout(30_000) : undefined),
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => null);
    const detail = typeof problem?.detail === "string" ? problem.detail : Array.isArray(problem?.detail)
      ? problem.detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.join(".") ?? "参数"}: ${item.msg ?? "无效"}`).join("\n") : undefined;
    throw new ApiError(detail ?? problem?.title ?? `请求失败 (${response.status})`, response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function post<T>(path: string, body?: unknown) {
  return api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
}

export function put<T>(path: string, body: unknown) {
  return api<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export async function uploadProjectAsset(projectId: string, file: File) {
  if (file.size > 50 * 1024 * 1024) throw new Error("素材超过 50 MB 限制");
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const sha256 = "sha256:" + Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  const intent = await post<{ uploadUrl: string }>("/assets/upload-intents", {
    projectId, fileName: file.name, mimeType: file.name.toLowerCase().endsWith(".glb") ? "model/gltf-binary" : file.type, sizeBytes: file.size, sha256,
  });
  const response = await fetch(intent.uploadUrl, { method: "PUT", body: file });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "素材上传失败");
  }
  return response.json();
}
