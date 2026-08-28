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

  it('runs the cross-grade check and shows a success notice when clean', async () => {
    stubGradesAndJobs()
    const checkSpy = vi.spyOn(api, 'checkExportAll').mockResolvedValue({ conflicts: [], skipped_grades: [] })
    const wrapper = mount(ExportAllSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="check-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(checkSpy).toHaveBeenCalledWith([
      { grade: '初三', job_id: 'job-3', candidate_index: 1 },
      { grade: '七年级', job_id: 'job-7', candidate_index: 1 },
    ])
    expect(wrapper.find('[data-test="notice"]').text()).toContain('校验通过')
  })

  it('shows conflicts and skipped grades from the check response', async () => {
    stubGradesAndJobs()
    vi.spyOn(api, 'checkExportAll').mockResolvedValue({
      conflicts: [{
        teacher: '王老师', day: '周一', grade_a: '初三', class_a: 1, course_a: '语文',
        start_a: '08:00', end_a: '08:45', grade_b: '七年级', class_b: 2, course_b: '数学',
        start_b: '07:50', end_b: '08:35',
      }],
      skipped_grades: ['八年级'],
    })
    const wrapper = mount(ExportAllSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="check-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="conflicts"]').text()).toContain('王老师')
    expect(wrapper.text()).toContain('八年级')
  })

  it('shows the backend error message when export fails due to conflicts', async () => {
    stubGradesAndJobs()
    vi.spyOn(api, 'exportAll').mockRejectedValue(new Error('跨年级校验未通过，存在 1 处教师时间冲突，不能导出'))
    const wrapper = mount(ExportAllSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="export-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('跨年级校验未通过')
  })
})
