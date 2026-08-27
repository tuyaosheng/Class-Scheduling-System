import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import VenueOccupancyGrid from '../components/VenueOccupancyGrid.vue'
import * as api from '../api'

describe('VenueOccupancyGrid', () => {
  it('renders one column per venue and counts classes occupying it per slot', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [
        { name: '综实1', family: '物理', venue: '物理实验室', alternate: null, external: false },
        { name: '体育', family: '体育', venue: '操场', alternate: null, external: false },
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
      ],
    })
    vi.spyOn(api, 'getVenues').mockResolvedValue({
      venues: [{ name: '物理实验室', capacity: 3 }, { name: '操场', capacity: null }],
    })

    const wrapper = mount(VenueOccupancyGrid, {
      props: {
        placements: [
          { class_id: 1, course: '综实1', slot: 0 },
          { class_id: 2, course: '综实1', slot: 0 },
          { class_id: 3, course: '语文', slot: 0 },
        ],
        grade: '初三',
      },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('物理实验室')
    expect(wrapper.text()).toContain('操场')
    expect(wrapper.text()).toContain('2/3')
  })

  it('flags a slot as over capacity when the count exceeds it', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [{ name: '综实1', family: '物理', venue: '物理实验室', alternate: null, external: false }],
    })
    vi.spyOn(api, 'getVenues').mockResolvedValue({
      venues: [{ name: '物理实验室', capacity: 1 }],
    })

    const wrapper = mount(VenueOccupancyGrid, {
      props: {
        placements: [
          { class_id: 1, course: '综实1', slot: 0 },
          { class_id: 2, course: '综实1', slot: 0 },
        ],
        grade: '初三',
      },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('.cell-over').exists()).toBe(true)
    expect(wrapper.find('.cell-over').text()).toBe('2/1')
  })

  it('shows an empty hint when no venues are configured', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    vi.spyOn(api, 'getVenues').mockResolvedValue({ venues: [] })

    const wrapper = mount(VenueOccupancyGrid, { props: { placements: [], grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('尚未配置任何场地')
  })
})
