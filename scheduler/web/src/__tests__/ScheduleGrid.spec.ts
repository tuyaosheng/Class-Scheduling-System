import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleGrid from '../components/ScheduleGrid.vue'
import * as api from '../api'

describe('ScheduleGrid', () => {
  it('renders 45 time rows and one column per class', () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1, 2],
        placements: [
          { task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null },
          { task_id: 1, class_id: 2, course: '数学', slot: 0, parity: null },
        ],
      },
    })
    const rows = wrapper.findAll('[data-test="grid-row"]')
    expect(rows).toHaveLength(45)
    expect(wrapper.text()).toContain('语文')
    expect(wrapper.text()).toContain('数学')
  })

  it('respects a custom calendar shape instead of the hardcoded default', () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [],
        days: ['周一', '周二', '周三', '周四', '周五'],
        periodsPerDay: 8,
      },
    })
    expect(wrapper.findAll('[data-test="grid-row"]')).toHaveLength(40)
  })

  it('joins same-slot multi placements with a slash (单双周)', () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [
          { task_id: 0, class_id: 1, course: '美术', slot: 0, parity: '单周' },
          { task_id: 1, class_id: 1, course: '心理', slot: 0, parity: '双周' },
        ],
      },
    })
    expect(wrapper.text()).toContain('美术(单周)/心理(双周)')
  })

  it('dragging a course onto an empty cell stages a move without touching the backend', async () => {
    const adjustSpy = vi.spyOn(api, 'adjustCandidate')
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null }],
        jobId: 'job-1',
        candidateIndex: 1,
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')

    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')

    expect(cells[0].text()).toBe('')
    expect(cells[3].text()).toBe('语文')
    expect(adjustSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(true)
  })

  it('dragging onto an occupied cell swaps the two courses locally', async () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [
          { task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null },
          { task_id: 1, class_id: 1, course: '数学', slot: 3, parity: null },
        ],
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')

    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')

    expect(cells[0].text()).toBe('数学')
    expect(cells[3].text()).toBe('语文')
  })

  it('locks paired-parity cells: they are not draggable and reject drops', async () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [
          { task_id: 0, class_id: 1, course: '美术', slot: 0, parity: '单周' },
          { task_id: 1, class_id: 1, course: '语文', slot: 3, parity: null },
        ],
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')
    expect(cells[0].attributes('draggable')).toBe('false')

    // 从 slot 3（可拖）拖到 slot 0（锁定的配对格）——不应该生效。
    await cells[3].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[0].trigger('dragover')
    await cells[0].trigger('drop')

    expect(cells[0].text()).toBe('美术(单周)')
    expect(cells[3].text()).toBe('语文')
  })

  it('blocks cross-class drops', async () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1, 2],
        placements: [
          { task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null },
          { task_id: 1, class_id: 2, course: '数学', slot: 3, parity: null },
        ],
      },
    })
    // 每行两个 cell（1 班、2 班），第 0 行第一个是 1 班，第二个是 2 班。
    const row0 = wrapper.findAll('[data-test="grid-row"]')[0].findAll('.cell')
    const row3 = wrapper.findAll('[data-test="grid-row"]')[3].findAll('.cell')

    await row0[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })   // 拖 1 班的语文
    await row3[1].trigger('dragover')                          // 拖到 2 班同一行
    await row3[1].trigger('drop')

    expect(row0[0].text()).toBe('语文')   // 原位不变
    expect(row3[1].text()).toBe('数学')   // 目标格也不变
  })

  it('confirm calls adjustCandidate with the staged moves and redraws from the response', async () => {
    vi.spyOn(api, 'adjustCandidate').mockResolvedValue({
      applied: [{ task_id: 0, from_slot: 0, to_slot: 3 }],
      reverted: [],
      placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 3, parity: null }],
    })
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null }],
        jobId: 'job-1',
        candidateIndex: 1,
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')
    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')

    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.adjustCandidate).toHaveBeenCalledWith(
      'job-1', 1, 1, [{ task_id: 0, from_slot: 0, to_slot: 3 }],
    )
    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(false)
  })

  it('dragging one occurrence of a multi-period task leaves the other alone', async () => {
    // 回归测试：曾经真实发生过的 bug——语文周课时 2，两条 placement 共用
    // task_id=0。只拖第一节（slot 0），第二节（slot 5）不能被一起拖走。
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [
          { task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null },
          { task_id: 0, class_id: 1, course: '语文', slot: 5, parity: null },
        ],
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')
    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')

    expect(cells[0].text()).toBe('')
    expect(cells[3].text()).toBe('语文')
    expect(cells[5].text()).toBe('语文')   // 另一节纹丝不动，没被一起拖走
  })

  it('reverted moves bounce back and show the reason', async () => {
    vi.spyOn(api, 'adjustCandidate').mockResolvedValue({
      applied: [],
      reverted: [{ task_id: 0, from_slot: 0, reason: '教师分身：李老师同一时间在 3 班', kinds: ['教师分身'] }],
      placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null }],
    })
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null }],
        jobId: 'job-1',
        candidateIndex: 1,
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')
    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')
    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(cells[0].text()).toBe('语文')   // 弹回原位
    expect(cells[3].text()).toBe('')
    expect(wrapper.text()).toContain('教师分身：李老师同一时间在 3 班')
    const badge = wrapper.find('[data-test="revert-kind-badge"]')
    expect(badge.text()).toBe('教师分身')
    expect(badge.classes()).toContain('kind-structural')
  })

  it('cancel discards the staged moves without calling the backend', async () => {
    const adjustSpy = vi.spyOn(api, 'adjustCandidate')
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null }],
        jobId: 'job-1',
        candidateIndex: 1,
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')
    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')

    await wrapper.find('[data-test="cancel-button"]').trigger('click')

    expect(cells[0].text()).toBe('语文')
    expect(cells[3].text()).toBe('')
    expect(adjustSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(false)
  })

  it('resets staged moves when the placements prop changes (e.g. switching candidates)', async () => {
    const wrapper = mount(ScheduleGrid, {
      props: {
        classes: [1],
        placements: [{ task_id: 0, class_id: 1, course: '语文', slot: 0, parity: null }],
      },
    })
    const cells = wrapper.findAll('[data-test="grid-row"] .cell')
    await cells[0].trigger('dragstart', { dataTransfer: { setData: () => {} } })
    await cells[3].trigger('dragover')
    await cells[3].trigger('drop')
    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(true)

    await wrapper.setProps({
      placements: [{ task_id: 1, class_id: 1, course: '数学', slot: 0, parity: null }],
    })

    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(false)
    expect(cells[0].text()).toBe('数学')
  })
})
