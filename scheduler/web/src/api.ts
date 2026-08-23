export interface RuleEchoItem {
  raw: string
  parsed: string
}

export interface ImportPreview {
  token: string
  teachers: number
  classes: number
  tasks: number
  occupancy: number[]
  rule_engine: string
  rule_echo: Record<string, RuleEchoItem[]>
  warnings: string[]
  conflicts: Array<{
    class_id: number
    course: string
    from_teaching_table: string | null
    from_rules_sheet: string | null
  }>
}

export interface ConfigStatus {
  ready: boolean
  grade: string | null
  classes: number
  tasks: number
}

export interface PlanResponse {
  grade: string
  plan: Record<string, number>
  reserved_slots: number[][]
}

export interface SolveRequest {
  grade: string
  count: number
  min_diff: number
  max_seconds: number
}

export interface AiSettingsResponse {
  configured: boolean
  source: string
  masked_key: string | null
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, options)
  const body = await resp.json()
  if (!resp.ok) {
    throw new Error((body as { detail?: string }).detail ?? '请求失败')
  }
  return body as T
}

export async function importFiles(
  teachingFile: File, rulesFile: File, grade: string, ruleEngine: string,
): Promise<ImportPreview> {
  const form = new FormData()
  form.append('teaching_file', teachingFile)
  form.append('rules_file', rulesFile)
  const params = new URLSearchParams({ grade, rule_engine: ruleEngine })
  return request<ImportPreview>(`/api/import?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
}

export async function confirmImport(token: string) {
  return request<{ ok: boolean; teaching_path: string; rules_path: string }>(
    '/api/import/confirm',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) },
  )
}

export async function getConfigStatus() {
  return request<ConfigStatus>('/api/config/status')
}

export async function getPlan(grade: string) {
  const params = new URLSearchParams({ grade })
  return request<PlanResponse>(`/api/config/plan?${params.toString()}`)
}

export async function putPlan(grade: string, plan: Record<string, number>) {
  return request<PlanResponse>('/api/config/plan', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grade, plan }),
  })
}

export async function startSolve(body: SolveRequest) {
  return request<{ job_id: string }>('/api/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function connectSolveSocket(jobId: string, onEvent: (event: unknown) => void): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const socket = new WebSocket(`${proto}://${window.location.host}/api/ws/solve/${jobId}`)
  socket.onmessage = (ev) => onEvent(JSON.parse(ev.data))
  return socket
}

export async function getAiSettings() {
  return request<AiSettingsResponse>('/api/settings/ai')
}

export async function putAiSettings(apiKey: string) {
  return request<{ ok: boolean }>('/api/settings/ai', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
}

export async function testAiSettings() {
  return request<{ ok: boolean }>('/api/settings/ai/test', {
    method: 'POST',
  })
}

export function exportUrl(jobId: string, candidateIndex: number, template: boolean): string {
  return `/api/export/${jobId}/${candidateIndex}?template=${template ? 1 : 0}`
}
