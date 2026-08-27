import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RulesSettings from '../components/RulesSettings.vue'
import * as api from '../api'

describe('RulesSettings', () => {
  it('loads the current rules and renders one card per rule', async () => {
    vi.spyOn(api, 'getRules').mockResolvedValue({
      rules: [{
        type: 'teacher_max_run', scope: { grade: '初三' }, params: { max_len: 2 },
        mode: 'soft', enabled: true, weight: 10,
      }],
      rule_types: ['teacher_max_run', 'daily_min', 'daily_max'],
    })
    const wrapper = mount(RulesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    const rows = wrapper.findAll('[data-test="rule-row"]')
    expect(rows).toHaveLength(1)
    expect((wrapper.find('[data-test="rule-scope-grade"]').element as HTMLInputElement).value)
      .toBe('初三')
    expect((wrapper.find('[data-test="rule-params"]').element as HTMLTextAreaElement).value)
      .toBe('{"max_len":2}')
    expect(wrapper.find('[data-test="rule-weight"]').exists()).toBe(true)
  })

  it('hides the weight slider for hard rules', async () => {
    vi.spyOn(api, 'getRules').mockResolvedValue({
      rules: [{ type: 'daily_min', scope: {}, params: { n: 1 }, mode: 'hard', enabled: true, weight: 0 }],
      rule_types: ['daily_min'],
    })
    const wrapper = mount(RulesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="rule-weight"]').exists()).toBe(false)
  })

  it('adds a rule and saves the full list including it', async () => {
    vi.spyOn(api, 'getRules').mockResolvedValue({ rules: [], rule_types: ['daily_min'] })
    vi.spyOn(api, 'putRules').mockResolvedValue({
      rules: [{ type: 'daily_min', scope: { grade: '初三' }, params: { n: 1 },
               mode: 'hard', enabled: true, weight: 0 }],
      rule_types: ['daily_min'],
    })
    const wrapper = mount(RulesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-rule-button"]').trigger('click')
    await wrapper.find('[data-test="rule-scope-grade"]').setValue('初三')
    await wrapper.find('[data-test="rule-params"]').setValue('{"n": 1}')
    await wrapper.find('[data-test="save-rules-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putRules).toHaveBeenCalledWith([
      { type: 'daily_min', scope: { grade: '初三' }, params: { n: 1 }, mode: 'hard', enabled: true, weight: 0 },
    ])
    expect(wrapper.find('[data-test="notice"]').text()).toBe('已保存')
  })

  it('parses a comma-separated scope value into a list, coercing numeric class ids', async () => {
    vi.spyOn(api, 'getRules').mockResolvedValue({ rules: [], rule_types: ['daily_min'] })
    vi.spyOn(api, 'putRules').mockResolvedValue({ rules: [], rule_types: ['daily_min'] })
    const wrapper = mount(RulesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-rule-button"]').trigger('click')
    await wrapper.find('[data-test="rule-scope-class"]').setValue('1,2,3')
    await wrapper.find('[data-test="save-rules-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    const sent = (api.putRules as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][0] as Array<{ scope: Record<string, unknown> }>
    expect(sent[0].scope.class).toEqual([1, 2, 3])
  })

  it('shows an inline error and does not save when params is not valid JSON', async () => {
    vi.spyOn(api, 'getRules').mockResolvedValue({ rules: [], rule_types: ['daily_min'] })
    const putSpy = vi.spyOn(api, 'putRules')
    const wrapper = mount(RulesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-rule-button"]').trigger('click')
    await wrapper.find('[data-test="rule-params"]').setValue('{not json')
    await wrapper.find('[data-test="save-rules-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="error"]').text()).toContain('不是合法的 JSON')
  })

  it('removes a rule row', async () => {
    vi.spyOn(api, 'getRules').mockResolvedValue({
      rules: [{ type: 'daily_min', scope: {}, params: { n: 1 }, mode: 'hard', enabled: true, weight: 0 }],
      rule_types: ['daily_min'],
    })
    const wrapper = mount(RulesSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="remove-rule"]').trigger('click')
    expect(wrapper.findAll('[data-test="rule-row"]')).toHaveLength(0)
  })
})
