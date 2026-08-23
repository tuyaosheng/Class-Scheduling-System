import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AiSettings from '../components/AiSettings.vue'
import * as api from '../api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AiSettings', () => {
  it('shows 未配置 when no key', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: false, source: 'none', masked_key: null,
    })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="ai-status"]').text()).toContain('未配置')
  })

  it('shows local masked key when configured locally', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: true, source: 'local', masked_key: 'sk-s…cdef',
    })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))
    const status = wrapper.find('[data-test="ai-status"]').text()
    expect(status).toContain('已配置')
    expect(status).toContain('本地')
    expect(status).toContain('sk-s…cdef')
  })

  it('shows env source when only env var set', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: true, source: 'env', masked_key: null,
    })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="ai-status"]').text()).toContain('环境变量')
  })

  it('saves the key and refreshes status', async () => {
    const getSpy = vi.spyOn(api, 'getAiSettings')
    getSpy.mockResolvedValueOnce({
      configured: false, source: 'none', masked_key: null,
    })
    getSpy.mockResolvedValueOnce({
      configured: true, source: 'local', masked_key: 'sk-s…cdef',
    })
    vi.spyOn(api, 'putAiSettings').mockResolvedValue({ ok: true })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-key-input"]').setValue('sk-super-secret')
    await wrapper.find('[data-test="ai-save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.putAiSettings).toHaveBeenCalledWith('sk-super-secret')
    expect(wrapper.find('[data-test="notice"]').text()).toContain('已保存')
    expect(wrapper.find('[data-test="ai-status"]').text()).toContain('已配置')
  })

  it('rejects saving an empty key', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: false, source: 'none', masked_key: null,
    })
    vi.spyOn(api, 'putAiSettings')
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('请先填写 API key')
    expect(api.putAiSettings).not.toHaveBeenCalled()
  })

  it('shows error when saving fails', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: false, source: 'none', masked_key: null,
    })
    vi.spyOn(api, 'putAiSettings').mockRejectedValue(new Error('保存失败'))
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-key-input"]').setValue('sk-x')
    await wrapper.find('[data-test="ai-save-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('保存失败')
  })

  it('shows 连接成功 when test connection succeeds', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: false, source: 'none', masked_key: null,
    })
    vi.spyOn(api, 'testAiSettings').mockResolvedValue({ ok: true })
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-test-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="notice"]').text()).toContain('连接成功')
  })

  it('shows error when test connection fails', async () => {
    vi.spyOn(api, 'getAiSettings').mockResolvedValue({
      configured: false, source: 'none', masked_key: null,
    })
    vi.spyOn(api, 'testAiSettings').mockRejectedValue(new Error('401 未授权'))
    const wrapper = mount(AiSettings)
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="ai-test-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('401 未授权')
  })
})
