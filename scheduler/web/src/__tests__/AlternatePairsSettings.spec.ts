import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AlternatePairsSettings from '../components/AlternatePairsSettings.vue'
import * as api from '../api'

function stubCourses() {
  vi.spyOn(api, 'getCourses').mockResolvedValue({
    courses: [
      { name: '美术', family: '心美', venue: null, alternate: '单周', external: false },
      { name: '心理', family: '心美', venue: null, alternate: '双周', external: false },
      { name: '书法', family: '书法', venue: null, alternate: null, external: false },
      { name: '棋艺', family: '棋艺', venue: null, alternate: null, external: false },
    ],
  })
}

describe('AlternatePairsSettings', () => {
  it('shows the imported pair as read-only and lets manual pairs be edited', async () => {
    stubCourses()
    vi.spyOn(api, 'getAlternatePairs').mockResolvedValue({
      pairs: [{ family: '心美', single_course: '美术', double_course: '心理', editable: false }],
    })
    const wrapper = mount(AlternatePairsSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="readonly-pair"]').text()).toContain('美术')
    expect(wrapper.find('[data-test="readonly-pair"]').text()).toContain('心理')
    expect(wrapper.findAll('[data-test="pair-row"]')).toHaveLength(0)
  })

  it('adds a manual pair and saves it', async () => {
    stubCourses()
    vi.spyOn(api, 'getAlternatePairs').mockResolvedValue({ pairs: [] })
    const putSpy = vi.spyOn(api, 'putAlternatePairs').mockResolvedValue({
      pairs: [{ family: '书棋', single_course: '书法', double_course: '棋艺', editable: true }],
    })
    const wrapper = mount(AlternatePairsSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-pair-button"]').trigger('click')
    await wrapper.find('[data-test="pair-family"]').setValue('书棋')
    await wrapper.find('[data-test="pair-single"]').setValue('书法')
    await wrapper.find('[data-test="pair-double"]').setValue('棋艺')
    await wrapper.find('[data-test="save-pairs-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(putSpy).toHaveBeenCalledWith('初三', [
      { family: '书棋', single_course: '书法', double_course: '棋艺', editable: true },
    ])
    expect(wrapper.find('[data-test="notice"]').text()).toBe('已保存')
  })

  it('removes a manual pair row before saving', async () => {
    stubCourses()
    vi.spyOn(api, 'getAlternatePairs').mockResolvedValue({
      pairs: [{ family: '书棋', single_course: '书法', double_course: '棋艺', editable: true }],
    })
    const wrapper = mount(AlternatePairsSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.findAll('[data-test="pair-row"]')).toHaveLength(1)
    await wrapper.find('[data-test="remove-pair"]').trigger('click')
    expect(wrapper.findAll('[data-test="pair-row"]')).toHaveLength(0)
  })

  it('shows the backend error message when saving fails', async () => {
    stubCourses()
    vi.spyOn(api, 'getAlternatePairs').mockResolvedValue({ pairs: [] })
    vi.spyOn(api, 'putAlternatePairs').mockRejectedValue(new Error('课程 \'书法\' 被用在多个单双周配对里'))
    const wrapper = mount(AlternatePairsSettings, { props: { grade: '初三' } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="add-pair-button"]').trigger('click')
    await wrapper.find('[data-test="save-pairs-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="error"]').text()).toContain('被用在多个单双周配对里')
  })
})
