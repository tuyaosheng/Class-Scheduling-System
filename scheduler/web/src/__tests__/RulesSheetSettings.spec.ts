import { describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import RulesSheetSettings from '../components/RulesSheetSettings.vue'
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

describe('RulesSheetSettings', () => {
  it('parses an uploaded file into a preview without writing anything', async () => {
    const parseSpy = vi.spyOn(api, 'parseRulesSheet').mockResolvedValue({
      grade: '初三',
      rules: [{ type: 'forbid_slots', scope: { grade: '初三', teacher: '李琼' }, params: { slots: [[1, 1]] }, mode: 'hard' }],
      teacher_facts: [{ name: '李琼', duties: ['班主任'], forbidden: [[1, 1]] }],
      warnings: [],
      rule_echo: {
        不能排课节次: [{ raw: '周二上午不排课', parsed: '周二 1,2,3,4,5', ai_parsed: null, mismatch: false }],
        固定节次: [], 排课要求: [], 备注: [],
      },
      ai_reviewed: false,
    })
    const putSpy = vi.spyOn(api, 'putRulesSheet')
    const wrapper = mount(RulesSheetSettings, { props: { grade: '初三' } })

    await selectFile(wrapper, 'rules-sheet-file', '排课说明.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(parseSpy).toHaveBeenCalledWith('初三', expect.any(File))
    expect(wrapper.text()).toContain('周二上午不排课')
    expect(wrapper.text()).toContain('未启用')
    expect(putSpy).not.toHaveBeenCalled()
  })

  it('flags a mismatch between regex and AI review', async () => {
    vi.spyOn(api, 'parseRulesSheet').mockResolvedValue({
      grade: '初三',
      rules: [],
      teacher_facts: [],
      warnings: [],
      rule_echo: {
        不能排课节次: [{ raw: '周二上午不排课', parsed: '周二 1,2,3,4,5', ai_parsed: '周二 1', mismatch: true }],
        固定节次: [], 排课要求: [], 备注: [],
      },
      ai_reviewed: true,
    })
    const wrapper = mount(RulesSheetSettings, { props: { grade: '初三' } })

    await selectFile(wrapper, 'rules-sheet-file', '排课说明.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="rule-ai-mismatch"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('需确认')
    expect(wrapper.text()).toContain('已启用')
  })

  it('confirm sends the parsed rules and teacher facts, then clears the preview', async () => {
    vi.spyOn(api, 'parseRulesSheet').mockResolvedValue({
      grade: '初三',
      rules: [{ type: 'forbid_slots', scope: { grade: '初三', teacher: '李琼' }, params: { slots: [[1, 1]] }, mode: 'hard' }],
      teacher_facts: [{ name: '李琼', duties: ['班主任'], forbidden: [[1, 1]] }],
      warnings: [],
      rule_echo: { 不能排课节次: [], 固定节次: [], 排课要求: [], 备注: [] },
      ai_reviewed: false,
    })
    const putSpy = vi.spyOn(api, 'putRulesSheet').mockResolvedValue({ ok: true, rules_written: 1, teachers_updated: 1 })
    const wrapper = mount(RulesSheetSettings, { props: { grade: '初三' } })

    await selectFile(wrapper, 'rules-sheet-file', '排课说明.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.find('[data-test="confirm-rules-sheet-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).toHaveBeenCalledWith('初三',
      [{ type: 'forbid_slots', scope: { grade: '初三', teacher: '李琼' }, params: { slots: [[1, 1]] }, mode: 'hard' }],
      [{ name: '李琼', duties: ['班主任'], forbidden: [[1, 1]] }])
    expect(wrapper.find('[data-test="notice"]').text()).toContain('已写入 1 条规则')
  })

  it('shows the backend error message when parsing fails', async () => {
    vi.spyOn(api, 'parseRulesSheet').mockRejectedValue(new Error("排课说明中的学科 '冷门课' 不在课程目录里"))
    const wrapper = mount(RulesSheetSettings, { props: { grade: '初三' } })

    await selectFile(wrapper, 'rules-sheet-file', '排课说明.xlsx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('不在课程目录里')
  })
})
