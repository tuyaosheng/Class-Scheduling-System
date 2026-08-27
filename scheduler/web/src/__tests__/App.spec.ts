import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'
import * as api from '../api'

function stubGrades(names: Array<{ name: string; classes: number }> = [{ name: '初三', classes: 32 }]) {
  vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: names })
  vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
}

describe('App navigation', () => {
  it('lands on step 1 (年级与班级) by default', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: false, grade: null, classes: 0, tasks: 0 })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.findComponent({ name: 'GradesSettings' }).exists()).toBe(true)
  })

  it('populates the sidebar grade switcher from the grade list', async () => {
    stubGrades([{ name: '初三', classes: 32 }, { name: '初一', classes: 8 }])
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: false, grade: null, classes: 0, tasks: 0 })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const pills = wrapper.findAll('[data-test="grade-pill"]')
    expect(pills.map((p) => p.text())).toEqual(['初三', '初一'])
  })

  it('shows an error message instead of staying blank when getConfigStatus fails', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockRejectedValue(new Error('后端暂时不可用'))
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('后端暂时不可用')
  })

  it('clicking a nav step switches the main content', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: false, grade: null, classes: 0, tasks: 0 })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const steps = wrapper.findAll('[data-test="nav-step"]')
    await steps[4].trigger('click')   // 第 5 步：任课表
    expect(wrapper.findComponent({ name: 'ImportPanel' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'GradesSettings' }).exists()).toBe(false)
  })

  it('opening settings shows AiSettings and hides the step content; a nav click returns to it', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: false, grade: null, classes: 0, tasks: 0 })
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({ configured: false, source: 'none', masked_key: null })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="open-settings"]').trigger('click')
    expect(wrapper.findComponent({ name: 'AiSettings' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'GradesSettings' }).exists()).toBe(false)

    const steps = wrapper.findAll('[data-test="nav-step"]')
    await steps[0].trigger('click')
    expect(wrapper.findComponent({ name: 'AiSettings' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'GradesSettings' }).exists()).toBe(true)
  })

  it('step 5 shows as done in the sidebar once config status reports ready', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: true, grade: '初三', classes: 32, tasks: 384 })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const steps = wrapper.findAll('[data-test="nav-step"]')
    expect(steps[4].classes()).toContain('done')   // 第 5 步：任课表
  })

  it('reaching step 7 shows the solve panel and candidate tabs', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: true, grade: '初三', classes: 32, tasks: 384 })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const steps = wrapper.findAll('[data-test="nav-step"]')
    await steps[6].trigger('click')   // 第 7 步：排课与调整
    expect(wrapper.findComponent({ name: 'SolvePanel' }).exists()).toBe(true)
  })

  it('step 3 shows course settings and the weekly-plan editor for the active grade', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: false, grade: null, classes: 0, tasks: 0 })
    vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    vi.spyOn(api, 'getPlan').mockResolvedValue({ grade: '初三', plan: {}, reserved_slots: [] })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const steps = wrapper.findAll('[data-test="nav-step"]')
    await steps[2].trigger('click')   // 第 3 步：课程与学科系
    expect(wrapper.findComponent({ name: 'CourseSettings' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'SettingsPanel' }).exists()).toBe(true)
  })

  it('step 4 shows the alternate-week pairing settings for the active grade', async () => {
    stubGrades()
    vi.spyOn(api, 'getConfigStatus').mockResolvedValue({ ready: false, grade: null, classes: 0, tasks: 0 })
    vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    vi.spyOn(api, 'getAlternatePairs').mockResolvedValue({ pairs: [] })
    const wrapper = mount(App)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const steps = wrapper.findAll('[data-test="nav-step"]')
    await steps[3].trigger('click')   // 第 4 步：单双周设置
    expect(wrapper.findComponent({ name: 'AlternatePairsSettings' }).exists()).toBe(true)
  })
})
