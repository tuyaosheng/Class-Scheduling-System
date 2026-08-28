import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ExportAllSettings from '../components/ExportAllSettings.vue'
import * as api from '../api'

function stubGradesAndJobs() {
  vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初三', classes: 32 }, { name: '七年级', classes: 8 }] })
  vi.spyOn(api, 'listSolveJobs').mockResolvedValue({
    jobs: [
      { job_id: 'job-3', status: 'done', grade: '初三', created_at: '2026-08-28T00:00:00+00:00', candidate_count: 3 },
      { job_id: 'job-7', status: 'done', grade: '七年级', created_at: '2026-08-28T00:00:00+00:00', candidate_count: 2 },
    ],
  })
}

function stubBlobUrl() {
  URL.createObjectURL = vi.fn(() => 'blob:mock')
  URL.revokeObjectURL = vi.fn()
}

describe('ExportAllSettings', () => {
  it('preselects the first job per grade and shows candidate options', async () => {
    stubGradesAndJobs()
    const wrapper = mount(ExportAllSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const rows = wrapper.findAll('[data-test="grade-pick-row"]')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('初三')
    expect(wrapper.text()).toContain('七年级')
  })

  it('exports directly without a separate check step', async () => {
    stubGradesAndJobs()
    stubBlobUrl()
    const exportSpy = vi.spyOn(api, 'exportAll').mockResolvedValue(new Blob(['zip']))
    const wrapper = mount(ExportAllSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="export-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(exportSpy).toHaveBeenCalledWith([
      { grade: '初三', job_id: 'job-3', candidate_index: 1 },
      { grade: '七年级', job_id: 'job-7', candidate_index: 1 },
    ])
    expect(wrapper.find('[data-test="notice"]').text()).toContain('已导出')
  })

  it('shows the backend error message when export fails', async () => {
    stubGradesAndJobs()
    vi.spyOn(api, 'exportAll').mockRejectedValue(new Error('任务不存在'))
    const wrapper = mount(ExportAllSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="export-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('任务不存在')
  })
})
