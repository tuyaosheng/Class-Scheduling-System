import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleGrid from '../components/ScheduleGrid.vue'

describe('ScheduleGrid', () => {
  it('renders 45 time rows and one column per class', () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1, 2],
        placements: [
          { class_id: 1, course: '语文', slot: 0, parity: null },
          { class_id: 2, course: '数学', slot: 0, parity: null },
        ],
      },
    })
    const rows = wrapper.findAll('[data-test="grid-row"]')
    expect(rows).toHaveLength(45)
    expect(wrapper.text()).toContain('语文')
    expect(wrapper.text()).toContain('数学')
  })

  it('joins same-slot multi placements with a slash (单双周)', () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [
          { class_id: 1, course: '美术', slot: 0, parity: '单周' },
          { class_id: 1, course: '心理', slot: 0, parity: '双周' },
        ],
      },
    })
    expect(wrapper.text()).toContain('美术(单周)/心理(双周)')
  })
})
