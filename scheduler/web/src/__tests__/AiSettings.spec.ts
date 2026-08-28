import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AiSettings from '../components/AiSettings.vue'
import * as api from '../api'

afterEach(() => {
  vi.restoreAllMocks()
})

function stub(overrides: Partial<api.AiSettingsResponse> = {}) {
  vi.spyOn(api, 'getAiSettings').mockResolvedValue({
    provider: 'openai', openai_configured: false, openai_base_url: null,
    openai_model: null, openai_masked_key: null, anthropic_configured: false,
    anthropic_source: 'none', anthropic_masked_key: null,
    ...overrides,
  })
}

describe('AiSettings', () => {
  it('defaults to the openai tab and shows its saved fields', async () => {
    stub({ openai_configured: true, openai_base_url: 'https://example.com/v1', openai_model: 'gpt-test' })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="openai-fields"]').exists()).toBe(true)
    expect((wrapper.find('[data-test="openai-base-url-input"]').element as HTMLInputElement).value)
      .toBe('https://example.com/v1')
    expect((wrapper.find('[data-test="openai-model-input"]').element as HTMLInputElement).value).toBe('gpt-test')
    expect(wrapper.find('[data-test="provider-openai"]').text()).toContain('已配置')
  })

  it('switches to the anthropic tab and shows its status', async () => {
    stub({ anthropic_configured: true, anthropic_source: 'local', anthropic_masked_key: 'sk-a…cdef' })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="provider-anthropic"]').trigger('click')
    expect(wrapper.find('[data-test="anthropic-fields"]').exists()).toBe(true)
    const status = wrapper.find('[data-test="anthropic-status"]').text()
    expect(status).toContain('本地')
    expect(status).toContain('sk-a…cdef')
  })

  it('saves openai fields with the openai provider', async () => {
    stub()
    const putSpy = vi.spyOn(api, 'putAiSettings').mockResolvedValue({ ok: true })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="openai-base-url-input"]').setValue('https://svc.example.com/v1')
    await wrapper.find('[data-test="openai-model-input"]').setValue('gpt-test')
    await wrapper.find('[data-test="openai-key-input"]').setValue('sk-super-secret')
    await wrapper.find('[data-test="ai-save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).toHaveBeenCalledWith({
      provider: 'openai', openai_base_url: 'https://svc.example.com/v1',
      openai_api_key: 'sk-super-secret', openai_model: 'gpt-test',
    })
    expect(wrapper.find('[data-test="notice"]').text()).toContain('已保存')
  })

  it('saves the anthropic key with the anthropic provider once selected', async () => {
    stub()
    const putSpy = vi.spyOn(api, 'putAiSettings').mockResolvedValue({ ok: true })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="provider-anthropic"]').trigger('click')
    await wrapper.find('[data-test="anthropic-key-input"]').setValue('sk-ant-secret')
    await wrapper.find('[data-test="ai-save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).toHaveBeenCalledWith({ provider: 'anthropic', anthropic_api_key: 'sk-ant-secret' })
  })

  it('shows error when saving fails', async () => {
    stub()
    vi.spyOn(api, 'putAiSettings').mockRejectedValue(new Error('保存失败'))
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('保存失败')
  })

  it('shows 连接成功 when test connection succeeds', async () => {
    stub()
    vi.spyOn(api, 'testAiSettings').mockResolvedValue({ ok: true })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-test-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="notice"]').text()).toContain('连接成功')
  })

  it('shows error when test connection fails', async () => {
    stub()
    vi.spyOn(api, 'testAiSettings').mockRejectedValue(new Error('401 未授权'))
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-test-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('401 未授权')
  })
})
