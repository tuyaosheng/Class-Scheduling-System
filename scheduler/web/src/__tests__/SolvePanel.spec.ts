import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SolvePanel from '../components/SolvePanel.vue'
import * as api from '../api'

describe('SolvePanel', () => {
  it('starts a solve job and forwards candidate events from the socket', async () => {
    vi.spyOn(api, 'startSolve').mockResolvedValue({ job_id: 'job-1' })

    class FakeSocket {
      onmessage: ((ev: MessageEvent) => void) | null = null
      close() {}
    }
    const fakeSocket = new FakeSocket()
    vi.spyOn(api, 'connectSolveSocket').mockImplementation((_jobId, onEvent) => {
      fakeSocket.onmessage = (ev) => onEvent(JSON.parse(ev.data))
      return fakeSocket as unknown as WebSocket
    })

    const wrapper = mount(SolvePanel)
    await wrapper.find('[data-test="start-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.emitted('jobId')![0]).toEqual(['job-1'])

    fakeSocket.onmessage!({
      data: JSON.stringify({
        type: 'candidate', index: 1, status: 'OPTIMAL', wall_time: 0.4,
        violations: [], placements: [],
      }),
    } as MessageEvent)

    expect(wrapper.emitted('candidates')).toBeTruthy()
    const lastEmit = wrapper.emitted('candidates')!.at(-1)![0] as unknown[]
    expect(lastEmit).toHaveLength(1)
  })

  it('shows the backend error message when the socket emits an error event', async () => {
    vi.spyOn(api, 'startSolve').mockResolvedValue({ job_id: 'job-1' })

    class FakeSocket {
      onmessage: ((ev: MessageEvent) => void) | null = null
      close() {}
    }
    const fakeSocket = new FakeSocket()
    vi.spyOn(api, 'connectSolveSocket').mockImplementation((_jobId, onEvent) => {
      fakeSocket.onmessage = (ev) => onEvent(JSON.parse(ev.data))
      return fakeSocket as unknown as WebSocket
    })

    const wrapper = mount(SolvePanel)
    await wrapper.find('[data-test="start-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    fakeSocket.onmessage!({
      data: JSON.stringify({
        type: 'error', message: '求解任务异常终止（ValueError）：配置损坏',
      }),
    } as MessageEvent)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('求解出错：求解任务异常终止（ValueError）：配置损坏')
  })

  it('shows a clear error and re-enables the button when startSolve rejects', async () => {
    vi.spyOn(api, 'startSolve').mockRejectedValue(new Error('还没有导入任课数据，请先完成导入确认'))

    const wrapper = mount(SolvePanel)
    await wrapper.find('[data-test="start-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('还没有导入任课数据，请先完成导入确认')
    // 失败之后按钮必须恢复可点，不能永久卡在禁用状态。
    expect(
      (wrapper.find('[data-test="start-button"]').element as HTMLButtonElement).disabled,
    ).toBe(false)
  })

  it('shows the disconnect message when the socket closes before a done event', async () => {
    vi.spyOn(api, 'startSolve').mockResolvedValue({ job_id: 'job-1' })

    class FakeSocket {
      onmessage: ((ev: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      close() {}
    }
    const fakeSocket = new FakeSocket()
    vi.spyOn(api, 'connectSolveSocket').mockImplementation((_jobId, onEvent) => {
      fakeSocket.onmessage = (ev) => onEvent(JSON.parse(ev.data))
      return fakeSocket as unknown as WebSocket
    })

    const wrapper = mount(SolvePanel)
    await wrapper.find('[data-test="start-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    // 还没收到 'done' 就断线（后端崩了 / 网络断了）。
    fakeSocket.onclose!()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('连接断开')
    expect(wrapper.text()).toContain('/api/solve/job-1')
    expect(
      (wrapper.find('[data-test="start-button"]').element as HTMLButtonElement).disabled,
    ).toBe(false)
  })

  it('does not show the disconnect message when the socket closes cleanly after done', async () => {
    vi.spyOn(api, 'startSolve').mockResolvedValue({ job_id: 'job-1' })

    class FakeSocket {
      onmessage: ((ev: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      close() {}
    }
    const fakeSocket = new FakeSocket()
    vi.spyOn(api, 'connectSolveSocket').mockImplementation((_jobId, onEvent) => {
      fakeSocket.onmessage = (ev) => onEvent(JSON.parse(ev.data))
      return fakeSocket as unknown as WebSocket
    })

    const wrapper = mount(SolvePanel)
    await wrapper.find('[data-test="start-button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    fakeSocket.onmessage!({ data: JSON.stringify({ type: 'done', count: 0 }) } as MessageEvent)
    await wrapper.vm.$nextTick()
    fakeSocket.onclose!()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).not.toContain('连接断开')
  })

  it('closes the previous socket and ignores a second click while a job is in flight', async () => {
    vi.spyOn(api, 'startSolve').mockResolvedValue({ job_id: 'job-1' })

    class FakeSocket {
      onmessage: ((ev: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      closed = false
      close() {
        this.closed = true
      }
    }
    const fakeSocket = new FakeSocket()
    vi.spyOn(api, 'connectSolveSocket').mockImplementation((_jobId, onEvent) => {
      fakeSocket.onmessage = (ev) => onEvent(JSON.parse(ev.data))
      return fakeSocket as unknown as WebSocket
    })

    const wrapper = mount(SolvePanel)
    const button = wrapper.find('[data-test="start-button"]')
    await button.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    // 第一个任务还没结束（没有 'done'），按钮此时应该已经被禁用；
    // 再点一次不应该发起第二个 startSolve 调用。
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    await button.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(api.startSolve).toHaveBeenCalledTimes(1)

    fakeSocket.onmessage!({
      data: JSON.stringify({
        type: 'candidate', index: 1, status: 'OPTIMAL', wall_time: 0.1,
        violations: [], placements: [],
      }),
    } as MessageEvent)
    const lastEmit = wrapper.emitted('candidates')!.at(-1)![0] as unknown[]
    expect(lastEmit).toHaveLength(1)   // 只有一份候选列表在增长，没有重复
  })
})
