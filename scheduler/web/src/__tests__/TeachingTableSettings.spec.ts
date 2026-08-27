import { describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import TeachingTableSettings from '../components/TeachingTableSettings.vue'
import * as api from '../api'

function makeFile(name: string): File {
  return new File(['fake content'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

async function selectFile(wrapper: VueWrapper, testId: string, fileName: string) {
  const fileInput = wrapper.find(`[data-test="${testId}"]`)
  const input = fileInput.element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [makeFile(fileName)], writable: false, configurable: true })
  await fileInput.trigger('change')
}

describe('TeachingTableSettings', () => {
  it('renders the current matrix with one row per class and one column per course', async () => {
    vi.spyOn(api, 'getTeachingTable').mockResolvedValue({
      classes: [1, 2],
      courses: ['语文', '数学'],
      entries: [
        { class_id: 1, course: '语文', teacher: '李琼' },
        { class_id: 1, course: '数学', teacher: '徐仪涵' },
      ],
      warnings: [],
    })
    const wrapper = mount(TeachingTableSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    const rows = wrapper.findAll('[data-test="teaching-row"]')
    expect(rows).toHaveLength(2)
    const cells = rows[0].findAll('[data-test="teaching-cell"]')
    expect((cells[0].element as HTMLInputElement).value).toBe('李琼')
    expect((cells[1].element as HTMLInputElement).value).toBe('徐仪涵')
  })

  it('shows a hint instead of a table when no classes are declared yet', async () => {
    vi.spyOn(api, 'getTeachingTable').mockResolvedValue({ classes: [], courses: [], entries: [], warnings: [] })
    const wrapper = mount(TeachingTableSettings, { props: { grade: '初一' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('先在「年级与班级」设置班级数量')
  })

  it('editing a cell and saving sends the full updated entry list', async () => {
    vi.spyOn(api, 'getTeachingTable').mockResolvedValue({
      classes: [1],
      courses: ['语文', '数学'],
      entries: [{ class_id: 1, course: '语文', teacher: '李琼' }],
      warnings: [],
    })
    const putSpy = vi.spyOn(api, 'putTeachingTable').mockResolvedValue({
      classes: [1], courses: ['语文', '数学'],
      entries: [
        { class_id: 1, course: '语文', teacher: '李琼' },
        { class_id: 1, course: '数学', teacher: '徐仪涵' },
      ],
      warnings: [],
    })
    const wrapper = mount(TeachingTableSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    const cells = wrapper.findAll('[data-test="teaching-cell"]')
    await cells[1].setValue('徐仪涵')
    await wrapper.find('[data-test="save-teaching-table-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).toHaveBeenCalledWith('初三', [
      { class_id: 1, course: '语文', teacher: '李琼' },
      { class_id: 1, course: '数学', teacher: '徐仪涵' },
    ])
    expect(wrapper.find('[data-test="notice"]').text()).toBe('已保存')
  })

  it('uploading a file parses it into a preview without saving, and shows warnings', async () => {
    vi.spyOn(api, 'getTeachingTable').mockResolvedValue({ classes: [1], courses: ['语文'], entries: [], warnings: [] })
    const parseSpy = vi.spyOn(api, 'parseTeachingTable').mockResolvedValue({
      classes: [1], courses: ['语文'],
      entries: [{ class_id: 1, course: '语文', teacher: '新老师' }],
      warnings: ['1班占 7 格，课程计划为 8 格'],
    })
    const putSpy = vi.spyOn(api, 'putTeachingTable')
    const wrapper = mount(TeachingTableSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await selectFile(wrapper, 'teaching-table-file', '任课表.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(parseSpy).toHaveBeenCalledWith('初三', expect.any(File))
    expect((wrapper.find('[data-test="teaching-cell"]').element as HTMLInputElement).value).toBe('新老师')
    expect(wrapper.find('[data-test="warnings"]').text()).toContain('1班占 7 格')
    expect(putSpy).not.toHaveBeenCalled()
  })

  it('shows the backend error message when saving fails', async () => {
    vi.spyOn(api, 'getTeachingTable').mockResolvedValue({
      classes: [1], courses: ['语文'], entries: [], warnings: [],
    })
    vi.spyOn(api, 'putTeachingTable').mockRejectedValue(new Error('课程 \'冷门课\' 没有在课程计划里设置周课时'))
    const wrapper = mount(TeachingTableSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="save-teaching-table-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('没有在课程计划里设置周课时')
  })
})
