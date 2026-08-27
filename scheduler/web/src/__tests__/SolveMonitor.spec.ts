import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SolveMonitor from '../components/SolveMonitor.vue'

describe('SolveMonitor', () => {
  it('shows an empty hint when no candidate has an objective value', () => {
    const wrapper = mount(SolveMonitor, {
      props: {
        candidates: [{ index: 1, objective: null, stats: '' }],
        activeIndex: 1,
      },
    })
    expect(wrapper.text()).toContain('没有软约束目标值可展示')
  })

  it('renders one bar per candidate with an objective value', () => {
    const wrapper = mount(SolveMonitor, {
      props: {
        candidates: [
          { index: 1, objective: 12, stats: 'CpSolverResponse stats:\nstatus: OPTIMAL' },
          { index: 2, objective: 4, stats: 'CpSolverResponse stats:\nstatus: OPTIMAL' },
        ],
        activeIndex: 2,
      },
    })
    expect(wrapper.findAll('.bar-col')).toHaveLength(2)
    expect(wrapper.text()).toContain('方案1')
    expect(wrapper.text()).toContain('方案2')
    expect(wrapper.find('[data-test="solver-stats-text"]').text()).toContain('status: OPTIMAL')
  })

  it('shows a hint when the active candidate has no stats text', () => {
    const wrapper = mount(SolveMonitor, {
      props: {
        candidates: [{ index: 1, objective: 5, stats: '' }],
        activeIndex: 1,
      },
    })
    expect(wrapper.text()).toContain('没有可展示的求解器日志')
  })
})
