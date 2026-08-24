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

export interface CourseItem {
  name: string
  family: string
  venue: string | null
  alternate: string | null
  external: boolean
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

export async function getCourses() {
  return request<{ courses: CourseItem[] }>('/api/config/courses')
}

export async function putCourses(courses: CourseItem[]) {
  return request<{ courses: CourseItem[] }>('/api/config/courses', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ courses }),
  })
}

export interface ImportSessionSummary {
  token: string
  grade: string
  created_at: string
}

export async function listImports() {
  return request<{ imports: ImportSessionSummary[] }>('/api/imports')
}

export async function getImportDetail(token: string) {
  return request<ImportPreview>(`/api/imports/${token}`)
}

export async function deleteImport(token: string) {
  return request<{ ok: boolean }>(`/api/imports/${token}`, { method: 'DELETE' })
}

export async function clearImports() {
  return request<{ ok: boolean }>('/api/imports', { method: 'DELETE' })
}

export interface SolveJobSummary {
  job_id: string
  status: string
  grade: string
  created_at: string
  candidate_count: number
}

export interface Candidate {
  index: number
  status: string
  wall_time: number
  violations: unknown[]
  placements: Array<{ task_id: number; class_id: number; course: string; slot: number; parity: string | null }>
}

export interface SolveJobDetail {
  job_id: string
  status: string
  grade: string
  candidates: Candidate[]
  issues: unknown[]
  conflict: string | null
}

export async function listSolveJobs() {
  return request<{ jobs: SolveJobSummary[] }>('/api/solve/jobs')
}

export async function getSolveJobDetail(jobId: string) {
  return request<SolveJobDetail>(`/api/solve/${jobId}`)
}

export async function deleteSolveJob(jobId: string) {
  return request<{ ok: boolean }>(`/api/solve/${jobId}`, { method: 'DELETE' })
}

export async function clearSolveJobs() {
  return request<{ ok: boolean }>('/api/solve/jobs', { method: 'DELETE' })
}

export interface AdjustMove {
  task_id: number
  from_slot: number
  to_slot: number
}

export interface AdjustResponse {
  applied: AdjustMove[]
  reverted: Array<{ task_id: number; from_slot: number; reason: string }>
  placements: Array<{ task_id: number; class_id: number; course: string; slot: number; parity: string | null }>
}

export async function adjustCandidate(
  jobId: string, candidateIndex: number, classId: number, moves: AdjustMove[],
) {
  return request<AdjustResponse>(`/api/solve/${jobId}/candidates/${candidateIndex}/adjust`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ class_id: classId, moves }),
  })
}
