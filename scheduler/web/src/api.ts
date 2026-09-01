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

export interface RuleTextEchoItem {
  raw: string
  parsed: string
  ai_parsed: string | null
  mismatch: boolean
}

export interface RuleSheetParseResponse {
  grade: string
  rules: Array<Record<string, unknown>>
  teacher_facts: Array<{ name: string; duties: string[]; forbidden: number[][] }>
  warnings: string[]
  rule_echo: Record<string, RuleTextEchoItem[]>
  ai_reviewed: boolean
}

export interface RuleSheetPutResponse {
  ok: boolean
  rules_written: number
  teachers_updated: number
}

export async function parseRulesSheet(grade: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ grade })
  return request<RuleSheetParseResponse>(`/api/config/rules-sheet/parse?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
}

export async function putRulesSheet(
  grade: string, rules: Array<Record<string, unknown>>,
  teacherFacts: Array<{ name: string; duties: string[]; forbidden: number[][] }>,
) {
  return request<RuleSheetPutResponse>('/api/config/rules-sheet', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grade, rules, teacher_facts: teacherFacts }),
  })
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
  provider: string
  openai_configured: boolean
  openai_base_url: string | null
  openai_model: string | null
  openai_masked_key: string | null
  anthropic_configured: boolean
  anthropic_source: string
  anthropic_masked_key: string | null
}

export interface AiSettingsPutRequest {
  provider: string
  openai_base_url?: string
  openai_api_key?: string
  openai_model?: string
  anthropic_api_key?: string
}

export interface CourseItem {
  name: string
  family: string
  venue: string | null
  alternate: string | null
  external: boolean
}

export interface VenueItem {
  name: string
  capacity: number | null
  grade_capacity?: Record<string, number>
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

export async function putAiSettings(body: AiSettingsPutRequest) {
  return request<{ ok: boolean }>('/api/settings/ai', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

export async function getCourses(grade: string) {
  const params = new URLSearchParams({ grade })
  return request<{ courses: CourseItem[] }>(`/api/config/courses?${params.toString()}`)
}

export async function putCourses(grade: string, courses: CourseItem[]) {
  return request<{ courses: CourseItem[] }>('/api/config/courses', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grade, courses }),
  })
}

export async function getVenues() {
  return request<{ venues: VenueItem[] }>('/api/config/venues')
}

export interface AlternatePairItem {
  family: string
  single_course: string
  double_course: string
  editable: boolean
}

export async function getAlternatePairs(grade: string) {
  const params = new URLSearchParams({ grade })
  return request<{ pairs: AlternatePairItem[] }>(`/api/config/alternate-pairs?${params.toString()}`)
}

export async function putAlternatePairs(grade: string, pairs: AlternatePairItem[]) {
  return request<{ pairs: AlternatePairItem[] }>('/api/config/alternate-pairs', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grade, pairs }),
  })
}

export interface TeachingTableEntry {
  class_id: number
  course: string
  teacher: string
}

export interface TeachingTableResponse {
  classes: number[]
  courses: string[]
  entries: TeachingTableEntry[]
  warnings: string[]
}

export async function getTeachingTable(grade: string) {
  const params = new URLSearchParams({ grade })
  return request<TeachingTableResponse>(`/api/config/teaching-table?${params.toString()}`)
}

export async function parseTeachingTable(grade: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ grade })
  return request<TeachingTableResponse>(`/api/config/teaching-table/parse?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
}

export async function putTeachingTable(grade: string, entries: TeachingTableEntry[]) {
  return request<TeachingTableResponse>('/api/config/teaching-table', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grade, entries }),
  })
}

export async function putVenues(venues: VenueItem[]) {
  return request<{ venues: VenueItem[] }>('/api/config/venues', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ venues }),
  })
}

export interface GradeItem {
  name: string
  classes: number
}

export async function getGrades() {
  return request<{ grades: GradeItem[] }>('/api/config/grades')
}

export async function putGrades(grades: GradeItem[]) {
  return request<{ grades: GradeItem[] }>('/api/config/grades', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grades }),
  })
}

export interface ParsedCalendarSheet {
  sheet_name: string
  periods_per_day: number
  midday_break_after: number
  clock_times: Array<[string, string]>
}

export async function parseCalendarWorkbook(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ sheets: ParsedCalendarSheet[] }>('/api/config/calendars/parse', {
    method: 'POST',
    body: form,
  })
}

export interface CalendarItem {
  grade: string
  days: string[]
  periods_per_day: number
  midday_break_after: number
  clock_times: Array<[string, string]>
}

export async function getCalendar(grade: string) {
  return request<CalendarItem>(`/api/config/calendars/${encodeURIComponent(grade)}`)
}

export async function putCalendar(grade: string, body: {
  days?: string[]; periods_per_day: number; midday_break_after: number; clock_times: Array<[string, string]>
}) {
  return request<CalendarItem>(`/api/config/calendars/${encodeURIComponent(grade)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export interface RuleItem {
  type: string
  scope: Record<string, unknown>
  params: Record<string, unknown>
  mode: string
  enabled: boolean
  weight: number
  description?: string
}

export async function getRules() {
  return request<{ rules: RuleItem[]; rule_types: string[] }>('/api/config/rules')
}

export async function putRules(rules: RuleItem[]) {
  return request<{ rules: RuleItem[]; rule_types: string[] }>('/api/config/rules', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rules }),
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
  objective: number | null
  stats: string
  violations: Array<{ kind: string; detail: string }>
  placements: Array<{ task_id: number; class_id: number; course: string; teacher: string; slot: number; parity: string | null }>
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

export interface MergedSolveResultItem {
  grade: string
  job_id: string
  status: string
  wall_time: number
  violations: number
}

export async function solveMerged(grades: string[], maxSeconds: number) {
  return request<{ results: MergedSolveResultItem[] }>('/api/solve/merged', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grades, max_seconds: maxSeconds }),
  })
}

export async function clearSolveJobs() {
  return request<{ ok: boolean }>('/api/solve/jobs', { method: 'DELETE' })
}

export interface ExportSelectionItem {
  grade: string
  job_id: string
  candidate_index: number
}

export async function exportAll(selections: ExportSelectionItem[]): Promise<Blob> {
  const resp = await fetch('/api/export/all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selections }),
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? '导出失败')
  }
  return resp.blob()
}

export interface AdjustMove {
  task_id: number
  from_slot: number
  to_slot: number
}

export interface AdjustResponse {
  applied: AdjustMove[]
  reverted: Array<{ task_id: number; from_slot: number; reason: string; kinds: string[] }>
  placements: Array<{ task_id: number; class_id: number; course: string; slot: number; parity: string | null }>
}

export interface Finding {
  severity: string
  scope: Record<string, unknown>
  issue: string
  suggestion: string
}

export async function reviewCandidate(jobId: string, candidateIndex: number) {
  return request<{ findings: Finding[] }>(
    `/api/solve/${jobId}/candidates/${candidateIndex}/review`,
    { method: 'POST' },
  )
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
