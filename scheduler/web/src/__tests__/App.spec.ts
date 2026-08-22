import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'
import * as api from '../api'

describe('App state machine', () => {
  it('shows the import panel when no config is ready yet', async () => {
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({
      ready: false, grade: null, classes: 0, tasks: 0,
    })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.findComponent({ name: 'ImportPanel' }).exists()).toBe(true)
  })

  it('shows the settings panel directly when config is already ready', async () => {
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({
      ready: true, grade: '初三', classes: 32, tasks: 384,
    })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.findComponent({ name: 'SettingsPanel' }).exists()).toBe(true)
  })

  it('moves from configuring to the solve panel when the user proceeds', async () => {
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({
      ready: true, grade: '初三', classes: 32, tasks: 384,
    })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="proceed-to-solve"]').trigger('click')
    expect(wrapper.findComponent({ name: 'SolvePanel' }).exists()).toBe(true)
  })
})
