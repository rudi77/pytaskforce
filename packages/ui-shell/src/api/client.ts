/**
 * API client used by the management UI host AND by every UI plugin.
 *
 * The host configures auth + base URL exactly once at startup via
 * {@link configureApiClient}. After that, both the host and any plugin
 * call {@link apiFetch} (or {@link sseStream}) without having to
 * thread credentials through every component. This keeps plugins
 * decoupled from the host's settings/auth implementation while still
 * speaking to a single backend with consistent headers.
 */

export interface ApiClientConfig {
  /** Returns the API base URL ("" means same-origin). */
  getBaseUrl(): string;
  /** Returns the bearer token, or null/empty when none. */
  getToken(): string | null;
}

const NOOP_CONFIG: ApiClientConfig = {
  getBaseUrl: () => "",
  getToken: () => null,
};

let _config: ApiClientConfig = NOOP_CONFIG;

/** Install the host's auth + base-url providers. Call once at startup. */
export function configureApiClient(config: ApiClientConfig): void {
  _config = config;
}

/** Reset to the default no-op config. Used by tests. */
export function resetApiClient(): void {
  _config = NOOP_CONFIG;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;
  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const base = _config.getBaseUrl();
  const url = path.startsWith("http") ? path : `${base}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: unknown = undefined;
  try {
    payload = await response.json();
  } catch {
    /* ignore */
  }
  const obj =
    (payload as { code?: string; message?: string; detail?: string; details?: unknown }) ??
    {};
  const message = obj.message ?? obj.detail ?? response.statusText ?? "Request failed";
  return new ApiError(message, response.status, obj.code, obj.details);
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const { body, query, headers, ...rest } = opts;
  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders.set("Content-Type", "application/json");
  }
  const token = _config.getToken();
  if (token) finalHeaders.set("Authorization", `Bearer ${token}`);

  const response = await fetch(buildUrl(path, query), {
    ...rest,
    headers: finalHeaders,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export async function* sseStream(
  path: string,
  opts: RequestOptions = {},
  signal?: AbortSignal,
): AsyncGenerator<{ event?: string; data: string }, void, void> {
  const { body, query, headers, ...rest } = opts;
  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "text/event-stream");
  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders.set("Content-Type", "application/json");
  }
  const token = _config.getToken();
  if (token) finalHeaders.set("Authorization", `Bearer ${token}`);

  const response = await fetch(buildUrl(path, query), {
    method: "POST",
    ...rest,
    headers: finalHeaders,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw await parseError(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event: { event?: string; data: string } = { data: "" };
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event.event = line.slice(6).trim();
        else if (line.startsWith("data:")) event.data += line.slice(5).trim();
      }
      if (event.data) yield event;
    }
  }
}
