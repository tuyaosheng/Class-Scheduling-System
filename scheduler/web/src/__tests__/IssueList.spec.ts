import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import IssueList from '../components/IssueList.vue'

describe('IssueList', () => {
  it('renders nothing when there are no items', () => {
    const wrapper = mount(IssueList, { props: { title: '预检问题', items: [] } })
    expect(wrapper.find('.issue-list').exists()).toBe(false)
  })

  it('renders one line per item with the kind and detail', () => {
    const wrapper = mount(IssueList, {
      props: {
        title: '预检问题',
        items: [
          { kind: '教师超载', detail: '梁艳红需要48节，可用42格，缺6格' },
          { kind: '班级超载', detail: '3班周课时46节，超过每周总格数45' },
        ],
      },
    })
    expect(wrapper.text()).toContain('预检问题（2）')
    const items = wrapper.findAll('[data-test="issue-item"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('教师超载')
    expect(items[0].text()).toContain('梁艳红需要48节，可用42格，缺6格')
  })
})
