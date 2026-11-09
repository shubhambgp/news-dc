// Empty base = same origin (production behind Caddy). Dev sets http://localhost:8000.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export type Health = { status: 'ok' | 'degraded'; db: 'ok' | 'error'; version: string }

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${API_BASE}/api/v1/health`)
  if (!res.ok) throw new Error(`Health check failed: HTTP ${res.status}`)
  return res.json()
}
