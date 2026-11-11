/**
 * frontend/src/api/client.ts
 * Standard HTTP fetch client with error handling.
 */

const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { detail: await response.text() };
      }
      
      const errorMessage =
        (typeof errorData.detail === 'string'
          ? errorData.detail
          : Array.isArray(errorData.detail)
          ? errorData.detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ')
          : response.statusText) || `HTTP error ${response.status}`;

      throw new ApiError(errorMessage, response.status, errorData);
    }

    return await response.json();
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Network errors (e.g. backend down)
    throw new ApiError(
      err.message === 'Failed to fetch'
        ? 'Cannot reach backend server. Please verify FastAPI is running at http://127.0.0.1:8000'
        : err.message || 'An unexpected network error occurred.',
      0
    );
  }
}
