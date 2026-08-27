import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AiReviewPanel from '../components/AiReviewPanel.vue'
import * as api from '../api'

describe('AiReviewPanel', () => {
  it('shows findings after clicking the review button', async () => {
    vi.spyOn(api, 'reviewCandidate').mockResolvedValue({
      findings: [{
        severity: 'warning', scope: { class: 7, day: '周一' },
        issue: '7班周一有2节数学，规则只约束了下限', suggestion: '为数学系增加 daily_max: 1 规则',
      }],
    })
    const wrapper = mount(AiReviewPanel, { props: { jobId: 'job-1', candidateIndex: 1 } })

    await wrapper.find('[data-test="ai-review-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.reviewCandidate).toHaveBeenCalledWith('job-1', 1)
    const items = wrapper.findAll('[data-test="ai-finding-item"]')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('7班周一有2节数学，规则只约束了下限')
    expect(items[0].text()).toContain('为数学系增加 daily_max: 1 规则')
    expect(items[0].text()).toContain('class=7')
  })

  it('shows a good badge when there are no findings', async () => {
    vi.spyOn(api, 'reviewCandidate').mockResolvedValue({ findings: [] })
    const wrapper = mount(AiReviewPanel, { props: { jobId: 'job-1', candidateIndex: 1 } })

    await wrapper.find('[data-test="ai-review-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('AI 未发现规则未覆盖的问题')
  })

  it('shows an error message when the review request fails', async () => {
    vi.spyOn(api, 'reviewCandidate').mockRejectedValue(
      new Error('未配置 Anthropic API key：请先在「设置 → AI 设置」里填写'),
    )
    const wrapper = mount(AiReviewPanel, { props: { jobId: 'job-1', candidateIndex: 1 } })

    await wrapper.find('[data-test="ai-review-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="ai-review-error"]').text()).toContain('未配置 Anthropic API key')
  })
})
