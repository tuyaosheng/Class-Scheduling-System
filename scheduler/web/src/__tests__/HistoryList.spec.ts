import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import HistoryList from '../components/HistoryList.vue'

describe('HistoryList', () => {
  it('shows a loading state while loading', () => {
    const wrapper = mount(HistoryList, { props: { title: '历史记录', rows: [], loading: true } })
    expect(wrapper.text()).toContain('加载中')
  })

  it('shows an empty state when there is nothing to show', () => {
    const wrapper = mount(HistoryList, { props: { title: '历史记录', rows: [], loading: false } })
    expect(wrapper.text()).toContain('暂无历史记录')
  })

  it('renders one row per item and does not show the clear button when empty', () => {
    const wrapper = mount(HistoryList, {
      props: {
        title: '历史记录', loading: false,
        rows: [
          { id: 'a', label: '初三', sublabel: '2026-08-24T10:00:00Z' },
          { id: 'b', label: '初三', sublabel: '2026-08-24T09:00:00Z' },
        ],
      },
    })
    expect(wrapper.findAll('[data-test="history-row"]')).toHaveLength(2)
    expect(wrapper.find('[data-test="history-clear"]').exists()).toBe(true)
  })

  it('emits select when a row is clicked', async () => {
    const wrapper = mount(HistoryList, {
      props: {
        title: '历史记录', loading: false,
        rows: [{ id: 'a', label: '初三', sublabel: 'now' }],
      },
    })
    await wrapper.find('[data-test="history-select"]').trigger('click')
    expect(wrapper.emitted('select')![0]).toEqual(['a'])
  })

  it('emits delete for the right row without triggering select', async () => {
    const wrapper = mount(HistoryList, {
      props: {
        title: '历史记录', loading: false,
        rows: [{ id: 'a', label: '初三', sublabel: 'now' }],
      },
    })
    await wrapper.find('[data-test="history-delete"]').trigger('click')
    expect(wrapper.emitted('delete')![0]).toEqual(['a'])
    expect(wrapper.emitted('select')).toBeFalsy()
  })

  it('emits clear when the clear button is clicked', async () => {
    const wrapper = mount(HistoryList, {
      props: {
        title: '历史记录', loading: false,
        rows: [{ id: 'a', label: '初三', sublabel: 'now' }],
      },
    })
    await wrapper.find('[data-test="history-clear"]').trigger('click')
    expect(wrapper.emitted('clear')).toBeTruthy()
  })
})
