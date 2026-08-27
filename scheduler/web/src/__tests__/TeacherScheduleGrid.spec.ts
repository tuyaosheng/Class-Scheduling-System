import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TeacherScheduleGrid from '../components/TeacherScheduleGrid.vue'

describe('TeacherScheduleGrid', () => {
  it('defaults to the first teacher (by string sort order) and renders 45 rows', () => {
    const wrapper = mount(TeacherScheduleGrid, {
      props: {
        placements: [
          { class_id: 1, course: '语文', teacher: '张老师', slot: 0, parity: null },
          { class_id: 2, course: '数学', teacher: '李老师', slot: 3, parity: null },
        ],
      },
    })
    expect(wrapper.findAll('[data-test="grid-row"]')).toHaveLength(45)
    // 组件按 JS 默认 .sort()（UTF-16 码点）排序，不是拼音——'张' < '李'。
    expect((wrapper.find('[data-test="teacher-input"]').element as HTMLInputElement).value)
      .toBe('张老师')
    expect(wrapper.text()).toContain('1班语文')
  })

  it('switching the selected teacher shows that teacher\'s own schedule', async () => {
    const wrapper = mount(TeacherScheduleGrid, {
      props: {
        placements: [
          { class_id: 1, course: '语文', teacher: '张老师', slot: 0, parity: null },
          { class_id: 2, course: '数学', teacher: '李老师', slot: 0, parity: null },
        ],
      },
    })
    await wrapper.find('[data-test="teacher-input"]').setValue('张老师')
    expect(wrapper.text()).toContain('1班语文')
    expect(wrapper.text()).not.toContain('2班数学')
  })

  it('shows an empty hint when there are no placements at all', () => {
    const wrapper = mount(TeacherScheduleGrid, { props: { placements: [] } })
    expect(wrapper.text()).toContain('没有可展示的教师课表')
  })
})
