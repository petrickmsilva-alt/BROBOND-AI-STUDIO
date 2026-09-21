/**
 * Return the public origin used by every browser request.
 *
 * Development talks directly to the locally running FastAPI service. In a
 * production bundle the public Render URL is supplied through
 * NEXT_PUBLIC_API_URL. Keeping this decision here prevents authentication
 * redirects and API requests from drifting onto different origins.
 */
export function getApiBaseUrl(): string {
  if (process.env.NODE_ENV === 'development') {
    return 'http://localhost:8000';
  }

  const configuredUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configuredUrl) return configuredUrl.replace(/\/$/, '');

  if (process.env.NODE_ENV === 'production') {
    // Do not ever fall back to localhost in a production browser.
    return 'https://brobond-ai-api.onrender.com';
  }

  // Unit tests and other non-browser runtimes retain a same-origin base.
  return '';
}
