import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CourseSettings from '../components/CourseSettings.vue'
import * as api from '../api'

describe('CourseSettings', () => {
  it('loads the current catalog and renders one row per course', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
        { name: '体比', family: '体育', venue: '操场', alternate: null, external: true },
      ],
    })
    const wrapper = mount(CourseSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const rows = wrapper.findAll('[data-test="course-row"]')
    expect(rows).toHaveLength(2)
    expect((wrapper.findAll('[data-test="course-name"]')[1].element as HTMLInputElement).value)
      .toBe('体比')
    expect((wrapper.findAll('[data-test="course-external"]')[1].element as HTMLInputElement).checked)
      .toBe(true)
  })

  it('adds a blank row and saves the full list including it', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [{ name: '语文', family: '语文', venue: null, alternate: null, external: false }],
    })
    vi.spyOn(api, 'putCourses').mockResolvedValue({
      courses: [
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
        { name: '班会', family: '班会', venue: null, alternate: null, external: true },
      ],
    })
    const wrapper = mount(CourseSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-course-button"]').trigger('click')
    const nameInputs = wrapper.findAll('[data-test="course-name"]')
    await nameInputs[1].setValue('班会')
    const familyInputs = wrapper.findAll('[data-test="course-family"]')
    await familyInputs[1].setValue('班会')
    await wrapper.findAll('[data-test="course-external"]')[1].setValue(true)

    await wrapper.find('[data-test="save-courses-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putCourses).toHaveBeenCalledWith([
      { name: '语文', family: '语文', venue: null, alternate: null, external: false },
      { name: '班会', family: '班会', venue: null, alternate: null, external: true },
    ])
    expect(wrapper.text()).toContain('已保存')
  })

  it('removes a row before saving', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
        { name: '数学', family: '数学', venue: null, alternate: null, external: false },
      ],
    })
    vi.spyOn(api, 'putCourses').mockResolvedValue({ courses: [] })
    const wrapper = mount(CourseSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.findAll('[data-test="remove-course"]')[0].trigger('click')
    expect(wrapper.findAll('[data-test="course-row"]')).toHaveLength(1)

    await wrapper.find('[data-test="save-courses-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putCourses).toHaveBeenCalledWith([
      { name: '数学', family: '数学', venue: null, alternate: null, external: false },
    ])
  })

  it('shows the backend error message when saving fails', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [{ name: '语文', family: '语文', venue: null, alternate: null, external: false }],
    })
    vi.spyOn(api, 'putCourses').mockRejectedValue(new Error("课程名 '语文' 重复"))
    const wrapper = mount(CourseSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="save-courses-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('重复')
  })

  it('shows the backend error message when loading fails', async () => {
    vi.spyOn(api, 'getCourses').mockRejectedValue(new Error('后端暂时不可用'))
    const wrapper = mount(CourseSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('后端暂时不可用')
  })
})
