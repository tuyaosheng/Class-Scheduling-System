import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MergedSolveSettings from '../components/MergedSolveSettings.vue'
import * as api from '../api'

function stubGrades() {
  vi.spyOn(api, 'getGrades').mockResolvedValue({
    grades: [{ name: '初三', classes: 32 }, { name: '七年级', classes: 8 }, { name: '八年级', classes: 8 }],
  })
}

describe('MergedSolveSettings', () => {
  it('preselects all grades and runs a merged solve', async () => {
    stubGrades()
    const solveSpy = vi.spyOn(api, 'solveMerged').mockResolvedValue({
      results: [
        { grade: '初三', job_id: 'job-a', status: 'OPTIMAL', wall_time: 0.4, violations: 0 },
        { grade: '七年级', job_id: 'job-b', status: 'OPTIMAL', wall_time: 0.3, violations: 0 },
        { grade: '八年级', job_id: 'job-c', status: 'OPTIMAL', wall_time: 0.5, violations: 0 },
      ],
    })
    const wrapper = mount(MergedSolveSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="run-merged-solve-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(solveSpy).toHaveBeenCalledWith(['初三', '七年级', '八年级'], 60)
    const rows = wrapper.findAll('[data-test="merged-result-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('初三')
    expect(rows[0].text()).toContain('OPTIMAL')
  })

  it('only solves the grades left checked', async () => {
    stubGrades()
    const solveSpy = vi.spyOn(api, 'solveMerged').mockResolvedValue({
      results: [
        { grade: '初三', job_id: 'job-a', status: 'OPTIMAL', wall_time: 0.4, violations: 0 },
        { grade: '七年级', job_id: 'job-b', status: 'OPTIMAL', wall_time: 0.3, violations: 0 },
      ],
    })
    const wrapper = mount(MergedSolveSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="merged-grade-八年级"]').setValue(false)
    await wrapper.find('[data-test="run-merged-solve-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(solveSpy).toHaveBeenCalledWith(['初三', '七年级'], 60)
  })

  it('shows an inline error and does not call the API when fewer than 2 grades are picked', async () => {
    stubGrades()
    const solveSpy = vi.spyOn(api, 'solveMerged')
    const wrapper = mount(MergedSolveSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="merged-grade-七年级"]').setValue(false)
    await wrapper.find('[data-test="merged-grade-八年级"]').setValue(false)
    await wrapper.find('[data-test="run-merged-solve-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(solveSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="error"]').text()).toContain('至少需要选择 2 个年级')
  })

  it('shows the backend error message when the solve request fails', async () => {
    stubGrades()
    vi.spyOn(api, 'solveMerged').mockRejectedValue(new Error('初三 还没有求解过，无法合排'))
    const wrapper = mount(MergedSolveSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="run-merged-solve-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('还没有求解过')
  })
})
