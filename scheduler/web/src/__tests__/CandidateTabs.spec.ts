import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CandidateTabs from '../components/CandidateTabs.vue'
import * as api from '../api'

describe('CandidateTabs', () => {
  it('renders one tab per candidate and switches the shown grid', async () => {
    const candidates = [
      { index: 1, status: 'OPTIMAL', wall_time: 0.4, objective: null, stats: '', violations: [], placements: [
        { task_id: 0, class_id: 1, course: '语文', teacher: '张老师', slot: 0, parity: null },
      ] },
      { index: 2, status: 'OPTIMAL', wall_time: 0.5, objective: null, stats: '', violations: [], placements: [
        { task_id: 1, class_id: 1, course: '数学', teacher: '李老师', slot: 0, parity: null },
      ] },
    ]
    const wrapper = mount(CandidateTabs, {
      props: { candidates, jobId: 'job-1', classes: [1], grade: '初三' },
    })

    const tabs = wrapper.findAll('[data-test="candidate-tab"]')
    expect(tabs).toHaveLength(2)
    expect(wrapper.text()).toContain('语文')

    await tabs[1].trigger('click')
    expect(wrapper.text()).toContain('数学')
  })

  it('shows an export link for the active candidate', () => {
    const candidates = [
      { index: 1, status: 'OPTIMAL', wall_time: 0.4, objective: null, stats: '', violations: [], placements: [] },
    ]
    const wrapper = mount(CandidateTabs, {
      props: { candidates, jobId: 'job-1', classes: [1], grade: '初三' },
    })
    const link = wrapper.find('[data-test="export-link"]')
    expect(link.attributes('href')).toBe('/api/export/job-1/1?template=0')
  })

  it('shows the violation details for the active candidate', () => {
    const candidates = [
      { index: 1, status: 'FEASIBLE', wall_time: 0.4, objective: null, stats: '',
        violations: [{ kind: '教师分身', detail: '李老师同一时间在 1 班和 3 班' }],
        placements: [] },
    ]
    const wrapper = mount(CandidateTabs, {
      props: { candidates, jobId: 'job-1', classes: [1], grade: '初三' },
    })
    expect(wrapper.text()).toContain('教师分身')
    expect(wrapper.text()).toContain('李老师同一时间在 1 班和 3 班')
  })

  it('switches between the class/teacher/venue views', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    vi.spyOn(api, 'getVenues').mockResolvedValue({ venues: [] })
    const candidates = [
      { index: 1, status: 'OPTIMAL', wall_time: 0.4, objective: null, stats: '', violations: [], placements: [
        { task_id: 0, class_id: 1, course: '语文', teacher: '张老师', slot: 0, parity: null },
      ] },
    ]
    const wrapper = mount(CandidateTabs, {
      props: { candidates, jobId: 'job-1', classes: [1], grade: '初三' },
    })

    await wrapper.find('[data-test="view-teacher"]').trigger('click')
    expect(wrapper.find('[data-test="teacher-input"]').exists()).toBe(true)

    await wrapper.find('[data-test="view-venue"]').trigger('click')
    expect(wrapper.find('[data-test="teacher-input"]').exists()).toBe(false)

    await wrapper.find('[data-test="view-monitor"]').trigger('click')
    expect(wrapper.find('[data-test="teacher-input"]').exists()).toBe(false)

    await wrapper.find('[data-test="view-class"]').trigger('click')
    expect(wrapper.text()).toContain('语文')
  })
})
