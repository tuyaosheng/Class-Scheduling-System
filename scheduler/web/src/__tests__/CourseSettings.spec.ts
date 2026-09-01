import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CourseSettings from '../components/CourseSettings.vue'
import * as api from '../api'

function stubVenues() {
  vi.spyOn(api, 'getVenues').mockResolvedValue({ venues: [{ name: '操场', capacity: null }] })
}

describe('CourseSettings', () => {
  it('loads the current catalog for the given grade and renders one row per course', async () => {
    stubVenues()
    const getCoursesSpy = vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
        { name: '体比', family: '体育', venue: '操场', alternate: null, external: true },
      ],
    })
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getCoursesSpy).toHaveBeenCalledWith('初三')
    const rows = wrapper.findAll('[data-test="course-row"]')
    expect(rows).toHaveLength(2)
    expect((wrapper.findAll('[data-test="course-name"]')[1].element as HTMLInputElement).value)
      .toBe('体比')
    expect((wrapper.findAll('[data-test="course-external"]')[1].element as HTMLInputElement).checked)
      .toBe(true)
  })

  it('reloads the catalog when the grade prop changes', async () => {
    stubVenues()
    const getCoursesSpy = vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.setProps({ grade: '初一' })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getCoursesSpy).toHaveBeenCalledWith('初一')
  })

  it('adds a blank row and saves the full list including it', async () => {
    stubVenues()
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [{ name: '语文', family: '语文', venue: null, alternate: null, external: false }],
    })
    vi.spyOn(api, 'putCourses').mockResolvedValue({
      courses: [
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
        { name: '班会', family: '班会', venue: null, alternate: null, external: true },
      ],
    })
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-course-button"]').trigger('click')
    const nameInputs = wrapper.findAll('[data-test="course-name"]')
    await nameInputs[1].setValue('班会')
    const familyInputs = wrapper.findAll('[data-test="course-family"]')
    await familyInputs[1].setValue('班会')
    await wrapper.findAll('[data-test="course-external"]')[1].setValue(true)

    await wrapper.find('[data-test="save-courses-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putCourses).toHaveBeenCalledWith('初三', [
      { name: '语文', family: '语文', venue: null, alternate: null, external: false },
      { name: '班会', family: '班会', venue: null, alternate: null, external: true },
    ])
    expect(wrapper.text()).toContain('已保存')
  })

  it('removes a row before saving', async () => {
    stubVenues()
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [
        { name: '语文', family: '语文', venue: null, alternate: null, external: false },
        { name: '数学', family: '数学', venue: null, alternate: null, external: false },
      ],
    })
    vi.spyOn(api, 'putCourses').mockResolvedValue({ courses: [] })
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.findAll('[data-test="remove-course"]')[0].trigger('click')
    expect(wrapper.findAll('[data-test="course-row"]')).toHaveLength(1)

    await wrapper.find('[data-test="save-courses-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putCourses).toHaveBeenCalledWith('初三', [
      { name: '数学', family: '数学', venue: null, alternate: null, external: false },
    ])
  })

  it('shows the backend error message when saving fails', async () => {
    stubVenues()
    vi.spyOn(api, 'getCourses').mockResolvedValue({
      courses: [{ name: '语文', family: '语文', venue: null, alternate: null, external: false }],
    })
    vi.spyOn(api, 'putCourses').mockRejectedValue(new Error("课程名 '语文' 重复"))
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="save-courses-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('重复')
  })

  it('shows the backend error message when loading fails', async () => {
    stubVenues()
    vi.spyOn(api, 'getCourses').mockRejectedValue(new Error('后端暂时不可用'))
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('后端暂时不可用')
  })

  it('loads and saves venue capacities independently of the course catalog', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    vi.spyOn(api, 'getVenues').mockResolvedValue({
      venues: [{ name: '物理实验室', capacity: 3 }, { name: '操场', capacity: null }],
    })
    const putVenuesSpy = vi.spyOn(api, 'putVenues').mockResolvedValue({
      venues: [{ name: '物理实验室', capacity: 4 }, { name: '操场', capacity: null }],
    })
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    const capacityInputs = wrapper.findAll('[data-test="venue-capacity"]')
    expect((capacityInputs[0].element as HTMLInputElement).value).toBe('3')
    expect((capacityInputs[1].element as HTMLInputElement).value).toBe('')

    await capacityInputs[0].setValue('4')
    await wrapper.find('[data-test="save-venues-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putVenuesSpy).toHaveBeenCalledWith([
      { name: '物理实验室', capacity: 4, grade_capacity: {} },
      { name: '操场', capacity: null, grade_capacity: {} },
    ])
    expect(wrapper.find('[data-test="venue-notice"]').text()).toBe('已保存')
  })

  it('editing the grade-specific capacity preserves other grades\' overrides', async () => {
    vi.spyOn(api, 'getCourses').mockResolvedValue({ courses: [] })
    vi.spyOn(api, 'getVenues').mockResolvedValue({
      venues: [{ name: '操场', capacity: 6, grade_capacity: { 七年级: 2 } }],
    })
    const putVenuesSpy = vi.spyOn(api, 'putVenues').mockResolvedValue({
      venues: [{ name: '操场', capacity: 6, grade_capacity: { 七年级: 2, 初三: 3 } }],
    })
    const wrapper = mount(CourseSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    const gradeCapacityInput = wrapper.find('[data-test="venue-grade-capacity"]')
    expect((gradeCapacityInput.element as HTMLInputElement).value).toBe('')
    await gradeCapacityInput.setValue('3')
    await wrapper.find('[data-test="save-venues-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putVenuesSpy).toHaveBeenCalledWith([
      { name: '操场', capacity: 6, grade_capacity: { 七年级: 2, 初三: 3 } },
    ])
  })
})
