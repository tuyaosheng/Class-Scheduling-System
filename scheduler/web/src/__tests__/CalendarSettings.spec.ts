import { describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import CalendarSettings from '../components/CalendarSettings.vue'
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

describe('CalendarSettings', () => {
  it('shows the current calendar status for each grade', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初三', classes: 32 }, { name: '初一', classes: 8 }] })
    vi.spyOn(api, 'getCalendar').mockImplementation(async (grade: string) => {
      if (grade === '初三') {
        return { grade: '初三', days: ['周一'], periods_per_day: 9, midday_break_after: 5, clock_times: [] }
      }
      throw new Error('没有对应的日历配置')
    })
    const wrapper = mount(CalendarSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const rows = wrapper.findAll('[data-test="current-calendar-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('每天 9 节')
    expect(rows[1].text()).toContain('未导入')
  })

  it('parses an uploaded workbook and auto-guesses the grade when names match', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '七年级', classes: 8 }] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
    vi.spyOn(api, 'parseCalendarWorkbook').mockResolvedValue({
      sheets: [
        { sheet_name: '七年级', periods_per_day: 8, midday_break_after: 4,
          clock_times: [['8:25', '9:05'], ['16:50', '17:30']] },
      ],
    })
    const wrapper = mount(CalendarSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await selectFile(wrapper, 'calendar-file', '作息表.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="parsed-sheet"]').text()).toContain('每天 8 节')
    expect(wrapper.find('[data-test="parsed-sheet"]').text()).toContain('午休在第 4 节后')
    expect((wrapper.find('[data-test="sheet-grade-select"]').element as HTMLSelectElement).value).toBe('七年级')
  })

  it('writing a sheet to a grade calls putCalendar and removes it from the pending list', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初一', classes: 8 }] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
    vi.spyOn(api, 'parseCalendarWorkbook').mockResolvedValue({
      sheets: [
        { sheet_name: '七年级', periods_per_day: 8, midday_break_after: 4,
          clock_times: [['8:25', '9:05']] },
      ],
    })
    vi.spyOn(api, 'putCalendar').mockResolvedValue({
      grade: '初一', days: ['周一'], periods_per_day: 8, midday_break_after: 4, clock_times: [['8:25', '9:05']],
    })
    const wrapper = mount(CalendarSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await selectFile(wrapper, 'calendar-file', '作息表.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="sheet-grade-select"]').setValue('初一')
    await wrapper.find('[data-test="confirm-sheet"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putCalendar).toHaveBeenCalledWith('初一', {
      periods_per_day: 8, midday_break_after: 4, clock_times: [['8:25', '9:05']],
    })
    expect(wrapper.find('[data-test="parsed-sheet"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="notice"]').text()).toContain('初一')
  })

  it('shows an error when confirming without picking a grade', async () => {
    vi.spyOn(api, 'getGrades').mockResolvedValue({ grades: [{ name: '初一', classes: 8 }] })
    vi.spyOn(api, 'getCalendar').mockRejectedValue(new Error('not found'))
    vi.spyOn(api, 'parseCalendarWorkbook').mockResolvedValue({
      sheets: [{ sheet_name: '某个 sheet', periods_per_day: 8, midday_break_after: 4, clock_times: [] }],
    })
    const putSpy = vi.spyOn(api, 'putCalendar')
    const wrapper = mount(CalendarSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await selectFile(wrapper, 'calendar-file', '作息表.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="confirm-sheet"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="error"]').text()).toContain('选择')
  })
})
