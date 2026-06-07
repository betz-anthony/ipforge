export interface ApiError {
  message: string
  hint?: string
  detail?: string
  code?: string
}

/** Normalize an axios error into a consistent shape. Handles the structured
 *  envelope (detail is an object), legacy string detail, and network errors. */
export function apiError(err: any, fallback = 'Request failed'): ApiError {
  const d = err?.response?.data?.detail
  if (d && typeof d === 'object') {
    return { message: d.message ?? fallback, hint: d.hint, detail: d.detail, code: d.code }
  }
  if (typeof d === 'string') return { message: d }
  return { message: fallback }
}
