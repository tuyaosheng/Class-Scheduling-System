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
})
