import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import GradesSettings from '../components/GradesSettings.vue'
import * as api from '../api'

describe('GradesSettings', () => {
  it('loads the current grade list and shows calendar status per grade', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初三', classes: 32 }] })
    vi.spyOn(api, 'getCalendar').mockResolvedValue({
      grade: '初三', days: ['周一'], periods_per_day: 9, midday_break_after: 5, clock_times: [],
    })
    const wrapper = mount(GradesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const rows = wrapper.findAll('[data-test="grade-row"]')
    expect(rows).toHaveLength(1)
    expect((wrapper.find('[data-test="grade-name"]').element as HTMLInputElement).value).toBe('初三')
    expect(wrapper.find('[data-test="grade-classes-val"]').text()).toBe('32')
    expect(wrapper.find('[data-test="calendar-status"]').text()).toContain('作息已导入')
  })

  it('shows "未导入" when the grade has no calendar yet', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初一', classes: 8 }] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('年级 "初一" 没有对应的日历配置'))
    const wrapper = mount(GradesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="calendar-status"]').text()).toContain('作息未导入')
  })

  it('adds a grade row and saves the full list including it', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
    vi.spyOn(api, 'putGrades').mockResolvedValue({ grades: [{ name: '初一', classes: 1 }] })

    const wrapper = mount(GradesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-grade-button"]').trigger('click')
    await wrapper.find('[data-test="grade-name"]').setValue('初一')
    await wrapper.find('[data-test="save-grades-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putGrades).toHaveBeenCalledWith([{ name: '初一', classes: 1 }])
    expect(wrapper.find('[data-test="notice"]').text()).toBe('已保存')
  })

  it('the classes stepper increments and decrements but never below 1', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初一', classes: 1 }] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
    const wrapper = mount(GradesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="grade-classes-dec"]').trigger('click')
    expect(wrapper.find('[data-test="grade-classes-val"]').text()).toBe('1')

    await wrapper.find('[data-test="grade-classes-inc"]').trigger('click')
    expect(wrapper.find('[data-test="grade-classes-val"]').text()).toBe('2')
  })

  it('deleting a row requires a confirm click first', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初三', classes: 32 }] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
    const wrapper = mount(GradesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="remove-grade"]').trigger('click')
    expect(wrapper.findAll('[data-test="grade-row"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="confirm-delete"]').exists()).toBe(true)

    await wrapper.find('[data-test="confirm-delete"]').trigger('click')
    expect(wrapper.findAll('[data-test="grade-row"]')).toHaveLength(0)
  })

  it('shows an error and does not save when a grade name is blank', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [] })
    const putSpy = vi.spyOn(api, 'putGrades')
    const wrapper = mount(GradesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-grade-button"]').trigger('click')
    await wrapper.find('[data-test="save-grades-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="error"]').text()).toContain('不能为空')
  })
})
