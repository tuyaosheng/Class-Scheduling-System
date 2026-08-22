import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ImportPanel from '../components/ImportPanel.vue'
import * as api from '../api'

describe('ImportPanel', () => {
  it('disables confirm and shows conflicts when the preview has conflicts', async () => {
    vi.spyOn(api, 'importFiles').mockResolvedValue({
      token: 't1', teachers: 2, classes: 2, tasks: 2, occupancy: [37],
      rule_engine: 'regex',
      rule_echo: { 不能排课节次: [], 固定节次: [], 排课要求: [], 备注: [] },
      warnings: [],
      conflicts: [{ class_id: 5, course: '历史', from_teaching_table: '廖文峰', from_rules_sheet: '陈俊彪' }],
    })

    const wrapper = mount(ImportPanel)
    await wrapper.find('[data-test="teaching-file"]').setValue('')
    await wrapper.find('[data-test="rules-file"]').setValue('')
    // setValue 对 <input type="file"> 不填真实文件，这里改为直接触发组件方法验证流程
    await (wrapper.vm as unknown as { runImport: () => Promise<void> }).runImport()

    expect(wrapper.text()).toContain('廖文峰')
    expect(wrapper.text()).toContain('陈俊彪')
    const confirmButton = wrapper.find('[data-test="confirm-button"]')
    expect((confirmButton.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('emits confirmed after a conflict-free preview is confirmed', async () => {
    vi.spyOn(api, 'importFiles').mockResolvedValue({
      token: 't2', teachers: 1, classes: 1, tasks: 1, occupancy: [37],
      rule_engine: 'regex',
      rule_echo: { 不能排课节次: [{ raw: '周五上午不排课', parsed: '周五 1,2,3,4,5' }], 固定节次: [], 排课要求: [], 备注: [] },
      warnings: [],
      conflicts: [],
    })
    vi.spyOn(api, 'confirmImport').mockResolvedValue({
      ok: true, teaching_path: 'a.yaml', rules_path: 'b.yaml',
    })

    const wrapper = mount(ImportPanel)
    await (wrapper.vm as unknown as { runImport: () => Promise<void> }).runImport()
    expect(wrapper.text()).toContain('周五上午不排课')

    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.emitted('confirmed')).toBeTruthy()
    expect(wrapper.emitted('confirmed')![0][0]).toEqual({ teaching_path: 'a.yaml', rules_path: 'b.yaml' })
  })
})
