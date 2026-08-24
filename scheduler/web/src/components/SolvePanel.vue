<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  clearSolveJobs, connectSolveSocket, deleteSolveJob, getSolveJobDetail, listSolveJobs, startSolve,
  type Candidate, type SolveJobSummary,
} from '../api'
import HistoryList, { type HistoryRow } from './HistoryList.vue'

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
      loadHistory()
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

const historyRows = ref<HistoryRow[]>([])
const historyLoading = ref(false)

function toHistoryRows(rows: SolveJobSummary[]): HistoryRow[] {
  return rows.map((r) => ({
    id: r.job_id, label: `${r.grade} · ${r.status}`,
    sublabel: `${r.candidate_count} 个候选方案 · ${r.created_at}`,
  }))
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const resp = await listSolveJobs()
    historyRows.value = toHistoryRows(resp.jobs)
  } catch (err) {
    statusText.value = '历史记录加载失败：' + (err as Error).message
  } finally {
    historyLoading.value = false
  }
}

async function selectHistory(jobId: string) {
  try {
    const detail = await getSolveJobDetail(jobId)
    candidates.length = 0
    candidates.push(...detail.candidates)
    emit('jobId', jobId)
    emit('candidates', [...candidates])
    statusText.value = `已加载历史任务，共 ${candidates.length} 个候选方案`
  } catch (err) {
    statusText.value = '加载历史任务失败：' + (err as Error).message
  }
}

async function deleteHistory(jobId: string) {
  try {
    await deleteSolveJob(jobId)
    await loadHistory()
  } catch (err) {
    statusText.value = '删除失败：' + (err as Error).message
  }
}

async function clearHistory() {
  try {
    await clearSolveJobs()
    await loadHistory()
  } catch (err) {
    statusText.value = '清空失败：' + (err as Error).message
  }
}

onMounted(loadHistory)

const statusKind = computed<'good' | 'warning' | 'critical' | 'neutral'>(() => {
  const t = statusText.value
  if (!t) return 'neutral'
  if (t.startsWith('完成')) return 'good'
  if (t.includes('无解') || t.includes('出错') || t.includes('失败') || t.includes('断开')) return 'critical'
  if (t.includes('超时') || t.includes('预检未通过')) return 'warning'
  return 'neutral'
})
</script>

<template>
  <section class="card">
    <h2>排课</h2>
    <div class="solve-form">
      <label class="field">
        候选数量
        <input type="number" min="1" v-model.number="count" />
      </label>
      <label class="field">
        最小差异度
        <input type="number" min="1" v-model.number="minDiff" />
      </label>
      <button data-test="start-button" class="btn btn-primary" :disabled="running" @click="start">
        {{ running ? '排课中…' : '开始排课' }}
      </button>
    </div>
    <p v-if="statusText" class="badge" :class="`badge-${statusKind}`">
      {{ statusText }}
    </p>

    <HistoryList title="历史求解任务" :rows="historyRows" :loading="historyLoading"
                @select="selectHistory" @delete="deleteHistory" @clear="clearHistory" />
  </section>
</template>

<style scoped>
.solve-form {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 16px;
  margin: 16px 0 18px;
}

.solve-form .field input {
  width: 100px;
  font-variant-numeric: tabular-nums;
}

.solve-form .btn {
  align-self: flex-end;
}
</style>
