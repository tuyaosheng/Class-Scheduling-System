<script setup lang="ts">
import { ref } from 'vue'
import { connectSolveSocket, startSolve } from '../api'

interface Candidate {
  index: number
  status: string
  wall_time: number
  violations: unknown[]
  placements: Array<{ class_id: number; course: string; slot: number; parity: string | null }>
}

const emit = defineEmits<{ jobId: [id: string]; candidates: [payload: Candidate[]] }>()

const grade = ref('初三')
const count = ref(3)
const minDiff = ref(8)
const maxSeconds = ref(60)
const statusText = ref('')
const running = ref(false)
const candidates: Candidate[] = []

// 挂在组件作用域上，而不是每次 start() 局部变量——第二次点击时需要能关掉
// 上一个还没结束的 socket（见 finding I2 第 3 点：否则两个 socket 的
// candidate 回调都往同一个数组 push，产生重复/互相矛盾的候选列表）。
let socket: WebSocket | null = null

async function start() {
  // running 为 true 说明上一个任务还没收到终结事件；按钮本身也会被禁用，
  // 这里是双保险，防止用别的方式（比如回车提交表单）绕过按钮触发第二次。
  if (running.value) return

  if (socket) {
    socket.close()
    socket = null
  }

  running.value = true
  statusText.value = '排课中…'

  let jobId: string
  try {
    const resp = await startSolve({
      grade: grade.value, count: count.value, min_diff: minDiff.value, max_seconds: maxSeconds.value,
    })
    jobId = resp.job_id
  } catch (err) {
    // 400（比如「还没有导入任课数据」）等请求级失败必须落地成看得懂的提示，
    // 不能让 statusText 永远停在「排课中…」、promise 变成未处理的 rejection。
    statusText.value = '排课请求失败：' + (err as Error).message
    running.value = false
    return
  }

  emit('jobId', jobId)
  candidates.length = 0

  // 'done' 到达之前 socket 意外断开（后端崩了、网络断了）才算异常断线；
  // 'done' 之后自然关闭不该弹「连接断开」的提示，用这个标记区分两种情况。
  let finished = false

  const ws = connectSolveSocket(jobId, (event) => {
    const e = event as { type: string; [key: string]: unknown }
    if (e.type === 'precheck_failed') {
      statusText.value = '预检未通过，未进入求解器'
    } else if (e.type === 'solving') {
      statusText.value = '求解中…'
    } else if (e.type === 'candidate') {
      candidates.push(e as unknown as Candidate)
      emit('candidates', [...candidates])
    } else if (e.type === 'infeasible') {
      statusText.value = '无解：' + (e.conflict as string)
    } else if (e.type === 'timeout') {
      statusText.value = '求解超时：' + (e.message as string)
    } else if (e.type === 'error') {
      statusText.value = '求解出错：' + (e.message as string)
    } else if (e.type === 'done') {
      finished = true
      running.value = false
      statusText.value = `完成，共 ${candidates.length} 个候选方案`
    }
  })
  socket = ws

  const onDisconnect = () => {
    if (finished) return
    // 设计文档规定的断线提示原文，见
    // docs/superpowers/specs/2026-08-22-web前后端批次一-design.md 「断线」一节。
    statusText.value = `连接断开，刷新页面或稍后用 /api/solve/${jobId} 查最终状态`
    running.value = false
  }
  ws.onerror = onDisconnect
  ws.onclose = onDisconnect
}
</script>

<template>
  <section>
    <h2>排课</h2>
    <label>候选数量 <input type="number" min="1" v-model.number="count" /></label>
    <label>最小差异度 <input type="number" min="1" v-model.number="minDiff" /></label>
    <button data-test="start-button" :disabled="running" @click="start">开始排课</button>
    <p>{{ statusText }}</p>
  </section>
</template>
