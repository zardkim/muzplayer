export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code)
  }
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

const BASE = '/api/v1'

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown; keepalive?: boolean } = {},
): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method: options.method ?? 'GET',
      credentials: 'same-origin',
      headers: options.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      keepalive: options.keepalive, // lets a save finish while the page is being closed
    })
  } catch {
    throw new ApiError(0, 'network')
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    // backend errors carry only a code in `detail`; FastAPI validation errors carry a list
    const code = typeof data?.detail === 'string' ? data.detail : res.status === 422 ? 'validation' : 'unknown'
    if (res.status === 401 && !path.startsWith('/auth/login')) onUnauthorized()
    throw new ApiError(res.status, code)
  }
  return data as T
}

export const streamUrl = (trackId: number) => `${BASE}/tracks/${trackId}/stream`
export const coverUrl = (albumId: number, size: 'thumb' | 'large' = 'thumb') =>
  `${BASE}/albums/${albumId}/cover?size=${size}`

export const bookStreamUrl = (bookId: number, index: number) => `${BASE}/books/${bookId}/files/${index}/stream`
export const bookCoverUrl = (bookId: number, size: 'thumb' | 'large' = 'thumb') =>
  `${BASE}/books/${bookId}/cover?size=${size}`

export function query(params: Record<string, string | number | undefined | null>) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}
