import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CandidateTabs from '../components/CandidateTabs.vue'

describe('CandidateTabs', () => {
  it('renders one tab per candidate and switches the shown grid', async () => {
    const candidates = [
      { index: 1, status: 'OPTIMAL', wall_time: 0.4, violations: [], placements: [
        { task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null },
      ] },
      { index: 2, status: 'OPTIMAL', wall_time: 0.5, violations: [], placements: [
        { task_id: 1, class_id: 1, course: '数学', slot: 0, parity: null },
      ] },
    ]
    const wrapper = mount(CandidateTabs, {
      props: { candidates, jobId: 'job-1', classes: [1] },
    })

    const tabs = wrapper.findAll('[data-test="candidate-tab"]')
    expect(tabs).toHaveLength(2)
    expect(wrapper.text()).toContain('语文')

    await tabs[1].trigger('click')
    expect(wrapper.text()).toContain('数学')
  })

  it('shows an export link for the active candidate', () => {
    const candidates = [
      { index: 1, status: 'OPTIMAL', wall_time: 0.4, violations: [], placements: [] },
    ]
    const wrapper = mount(CandidateTabs, {
      props: { candidates, jobId: 'job-1', classes: [1] },
    })
    const link = wrapper.find('[data-test="export-link"]')
    expect(link.attributes('href')).toBe('/api/export/job-1/1?template=0')
  })
})
