import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  confirmImport, connectSolveSocket, exportUrl, getAiSettings, getConfigStatus,
  getCourses, getPlan, importFiles, putAiSettings, putCourses, putPlan, startSolve, testAiSettings,
} from '../api'

afterEach(() => {
  vi.restoreAllMocks()
})

function mockFetchOnce(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('importFiles', () => {
  it('posts multipart form data and returns parsed preview', async () => {
    const fetchMock = mockFetchOnce({ token: 't1', teachers: 1, classes: 1, tasks: 1 })
    const teaching = new File(['x'], '任课表.xlsx')
    const rules = new File(['y'], '排课说明.xlsx')

    const preview = await importFiles(teaching, rules, '初三', 'regex')

    expect(preview.token).toBe('t1')
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/import')
    expect(url).toContain('grade=%E5%88%9D%E4%B8%89')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
  })

  it('throws with backend detail message on non-2xx response', async () => {
    mockFetchOnce({ detail: '两份文件存在教师归属冲突' }, 400)
    const teaching = new File(['x'], 'a.xlsx')
    const rules = new File(['y'], 'b.xlsx')
    await expect(importFiles(teaching, rules, '初三', 'regex'))
      .rejects.toThrow('两份文件存在教师归属冲突')
  })
})

describe('confirmImport / getConfigStatus / getPlan / putPlan / startSolve', () => {
  it('confirmImport posts the token', async () => {
    const fetchMock = mockFetchOnce({ ok: true, teaching_path: 'a', rules_path: 'b' })
    await confirmImport('tok')
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/import/confirm')
    expect(JSON.parse(options.body)).toEqual({ token: 'tok' })
  })

  it('getConfigStatus performs a GET', async () => {
    mockFetchOnce({ ready: true, grade: '初三', classes: 32, tasks: 384 })
    const status = await getConfigStatus()
    expect(status.ready).toBe(true)
  })

  it('getPlan and putPlan round-trip through the API', async () => {
    mockFetchOnce({ grade: '初三', plan: { 语文: 7 }, reserved_slots: [] })
    const got = await getPlan('初三')
    expect(got.plan.语文).toBe(7)

    const fetchMock = mockFetchOnce({ grade: '初三', plan: { 语文: 8 }, reserved_slots: [] })
    await putPlan('初三', { 语文: 8 })
    const [, options] = fetchMock.mock.calls[0]
    expect(options.method).toBe('PUT')
  })

  it('startSolve posts the solve request and returns a job id', async () => {
    mockFetchOnce({ job_id: 'job-1' })
    const { job_id } = await startSolve({ grade: '初三', count: 3, min_diff: 8, max_seconds: 60 })
    expect(job_id).toBe('job-1')
  })
})

describe('ai settings', () => {
  it('getAiSettings performs a GET and returns source', async () => {
    mockFetchOnce({ configured: true, source: 'local', masked_key: 'sk-s…cdef' })
    const settings = await getAiSettings()
    expect(settings.configured).toBe(true)
    expect(settings.source).toBe('local')
  })

  it('putAiSettings posts the key', async () => {
    const fetchMock = mockFetchOnce({ ok: true })
    await putAiSettings('sk-abc')
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/settings/ai')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({ api_key: 'sk-abc' })
  })

  it('testAiSettings posts and returns ok', async () => {
    const fetchMock = mockFetchOnce({ ok: true })
    const result = await testAiSettings()
    expect(result.ok).toBe(true)
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
  })
})

describe('courses', () => {
  it('getCourses performs a GET and returns the catalog', async () => {
    mockFetchOnce({ courses: [{ name: '语文', family: '语文', venue: null, alternate: null, external: false }] })
    const { courses } = await getCourses()
    expect(courses[0].name).toBe('语文')
  })

  it('putCourses posts the full course list', async () => {
    const fetchMock = mockFetchOnce({ courses: [] })
    await putCourses([{ name: '班会', family: '班会', venue: null, alternate: null, external: true }])
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/config/courses')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({
      courses: [{ name: '班会', family: '班会', venue: null, alternate: null, external: true }],
    })
  })
})

describe('connectSolveSocket', () => {
  it('creates a WebSocket pointed at the job id and wires onmessage', () => {
    class FakeSocket {
      url: string
      onmessage: ((ev: MessageEvent) => void) | null = null
      constructor(url: string) { this.url = url }
    }
    vi.stubGlobal('WebSocket', FakeSocket as unknown as typeof WebSocket)

    const events: unknown[] = []
    const socket = connectSolveSocket('job-1', (event) => events.push(event)) as unknown as FakeSocket
    expect(socket.url).toContain('/api/ws/solve/job-1')

    socket.onmessage!({ data: JSON.stringify({ type: 'solving' }) } as MessageEvent)
    expect(events).toEqual([{ type: 'solving' }])
  })
})

describe('exportUrl', () => {
  it('builds the export URL with optional template flag', () => {
    expect(exportUrl('job-1', 1, false)).toBe('/api/export/job-1/1?template=0')
    expect(exportUrl('job-1', 2, true)).toBe('/api/export/job-1/2?template=1')
  })
})
