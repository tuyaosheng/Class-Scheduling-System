import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsPanel from '../components/SettingsPanel.vue'
import * as api from '../api'

describe('SettingsPanel', () => {
  it('loads the current plan and renders one input per course', async () => {
    vi.spyOn(api, 'getPlan').mockResolvedValue({
      grade: '初三', plan: { 语文: 7, 数学: 5 }, reserved_slots: [[0, 9]],
    })
    const wrapper = mount(SettingsPanel, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    const inputs = wrapper.findAll('input[type="number"]')
    expect(inputs).toHaveLength(2)
    expect((inputs[0].element as HTMLInputElement).value).toBe('7')
  })

  it('saves the edited plan and emits saved on success', async () => {
    vi.spyOn(api, 'getPlan').mockResolvedValue({
      grade: '初三', plan: { 语文: 7 }, reserved_slots: [],
    })
    vi.spyOn(api, 'putPlan').mockResolvedValue({
      grade: '初三', plan: { 语文: 8 }, reserved_slots: [],
    })
    const wrapper = mount(SettingsPanel, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('input[type="number"]').setValue(8)
    await wrapper.find('[data-test="save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putPlan).toHaveBeenCalledWith('初三', { 语文: 8 })
    expect(wrapper.emitted('saved')).toBeTruthy()
  })

  it('shows the backend error message when saving fails', async () => {
    vi.spyOn(api, 'getPlan').mockResolvedValue({
      grade: '初三', plan: { 语文: 40 }, reserved_slots: [],
    })
    vi.spyOn(api, 'putPlan').mockRejectedValue(new Error('初三 每班周课时 40 超出可用 37 格'))
    const wrapper = mount(SettingsPanel, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('超出可用 37 格')
  })

  it('shows the backend error message when loading plan fails', async () => {
    vi.spyOn(api, 'getPlan').mockRejectedValue(new Error('后端暂时不可用'))
    const wrapper = mount(SettingsPanel, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('后端暂时不可用')
  })
})
