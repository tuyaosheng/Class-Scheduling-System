import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  it('renders the app shell heading', () => {
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('排课系统')
  })
})
