// API base: same-origin `/api/v1` by default (local FastAPI via the Vite proxy
// or a same-origin reverse proxy). When the SPA is hosted separately from the
// API - for example a Cloudflare Worker serving `dist/` with the FastAPI
// backend on Render - set VITE_API_BASE to the API origin, e.g.
// https://vbase-api.onrender.com/api/v1
const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "/api/v1";

export type ApiInit = RequestInit & {
  params?: Record<string, string | number | boolean | undefined | null | Array<string | number>>;
  /** Set to false to omit the CSRF header (never needed in practice). */
  csrf?: boolean;
};

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  status: number;
  data: unknown;
  requestId?: string;

  constructor(message: string, status: number, data: unknown, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.requestId = requestId;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function buildUrl(endpoint: string, params?: ApiInit["params"]): string {
  const url = `${API_BASE}${endpoint}`;
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) qs.append(key, String(item));
    } else {
      qs.append(key, String(value));
    }
  }
  const query = qs.toString();
  return query ? `${url}?${query}` : url;
}

async function request(endpoint: string, options: ApiInit = {}) {
  const { params, csrf = true, ...init } = options;
  const method = (init.method || "GET").toUpperCase();
  const url = buildUrl(endpoint, params);
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...((init.headers as Record<string, string>) || {}),
  };

  // CSRF double-submit token: the server issues a readable `vbase_csrf` cookie
  // alongside the HttpOnly session cookie, and every unsafe request must echo
  // it back in this header.
  if (csrf && MUTATING.has(method)) {
    const token = readCookie("vbase_csrf");
    if (token) headers["X-CSRF-Token"] = token;
  }

  const response = await fetch(url, { ...init, headers, credentials: "include" });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null);

  if (!response.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in (data as object)
        ? String((data as { detail: unknown }).detail)
        : null) ||
      (data && typeof data === "object" && "message" in (data as object)
        ? String((data as { message: unknown }).message)
        : null) ||
      response.statusText ||
      "Request failed";
    throw new ApiError(detail, response.status, data, response.headers.get("x-request-id") || undefined);
  }

  return data;
}

function encodeBody(body?: unknown): BodyInit | undefined {
  if (body === undefined || body === null) return undefined;
  if (typeof FormData !== "undefined" && body instanceof FormData) return body;
  if (typeof body === "string") return body;
  return JSON.stringify(body);
}

export const api = {
  get: <T>(endpoint: string, init?: ApiInit) =>
    request(endpoint, { ...init, method: "GET" }) as Promise<T>,
  post: <T>(endpoint: string, body?: unknown, init?: ApiInit) =>
    request(endpoint, { ...init, method: "POST", body: encodeBody(body) }) as Promise<T>,
  patch: <T>(endpoint: string, body?: unknown, init?: ApiInit) =>
    request(endpoint, { ...init, method: "PATCH", body: encodeBody(body) }) as Promise<T>,
  put: <T>(endpoint: string, body?: unknown, init?: ApiInit) =>
    request(endpoint, { ...init, method: "PUT", body: encodeBody(body) }) as Promise<T>,
  delete: <T>(endpoint: string, init?: ApiInit) =>
    request(endpoint, { ...init, method: "DELETE" }) as Promise<T>,
};

/** Download a URL that requires the session cookie. */
export async function downloadFile(endpoint: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE}${endpoint}`, { credentials: "include" });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail || detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail || "Download failed", response.status, null);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export const apiBase = API_BASE;
