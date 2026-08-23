<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getConfigStatus } from './api'
import AiSettings from './components/AiSettings.vue'
import ImportPanel from './components/ImportPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import SolvePanel from './components/SolvePanel.vue'
import CandidateTabs from './components/CandidateTabs.vue'

type Stage = 'idle' | 'needs_import' | 'configuring' | 'ready'
type Tab = 'scheduler' | 'settings'

interface Candidate {
  index: number
  status: string
  wall_time: number
  violations: unknown[]
  placements: Array<{ class_id: number; course: string; slot: number; parity: string | null }>
}

const stage = ref<Stage>('idle')
const tab = ref<Tab>('scheduler')
const grade = ref('初三')
const classes = ref<number[]>([])
const candidates = ref<Candidate[]>([])
const jobId = ref<string | null>(null)
const error = ref('')

onMounted(async () => {
  error.value = ''
  try {
    const status = await getConfigStatus()
    if (status.ready) {
      grade.value = status.grade ?? '初三'
      stage.value = 'configuring'
    } else {
      stage.value = 'needs_import'
    }
  } catch (err) {
    // 后端起不来 / 网络错误：不能让 await 无人接住，否则页面永远停在只有
    // <h1> 的空白状态。退回 needs_import 让用户至少看到导入面板和错误原因，
    // 而不是猜不出到底发生了什么（见 finding I1，与 SettingsPanel 同一模式）。
    error.value = (err as Error).message
    stage.value = 'needs_import'
  }
})

function onImportConfirmed() {
  stage.value = 'configuring'
}

function proceedToSolve() {
  stage.value = 'ready'
}

function onCandidates(payload: Candidate[]) {
  candidates.value = payload
  for (const c of payload) {
    for (const p of c.placements) {
      if (!classes.value.includes(p.class_id)) classes.value.push(p.class_id)
    }
  }
  classes.value.sort((a, b) => a - b)
}

function onJobId(id: string) {
  jobId.value = id
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <h1>排课系统</h1>
      <nav class="tab-nav">
        <button data-test="tab-scheduler" class="tab-nav__item" :class="{ active: tab === 'scheduler' }"
                @click="tab = 'scheduler'">排课</button>
        <button data-test="tab-settings" class="tab-nav__item" :class="{ active: tab === 'settings' }"
                @click="tab = 'settings'">设置</button>
      </nav>
    </header>

    <main class="app-content">
      <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>

      <template v-if="tab === 'settings'">
        <AiSettings />
      </template>

      <template v-if="tab === 'scheduler'">
        <ImportPanel v-if="stage === 'needs_import'" @confirmed="onImportConfirmed" />

        <template v-if="stage === 'configuring'">
          <SettingsPanel :grade="grade" />
          <button data-test="proceed-to-solve" class="btn btn-primary proceed-btn" @click="proceedToSolve">前往排课</button>
        </template>

        <template v-if="stage === 'ready'">
          <SolvePanel @job-id="onJobId" @candidates="onCandidates" />
          <CandidateTabs :candidates="candidates" :job-id="jobId" :classes="classes" />
        </template>
      </template>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 16px 32px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border);
}

.app-header h1 {
  font-size: 18px;
  color: var(--text-primary);
}

.tab-nav {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: var(--page-bg);
  border-radius: 999px;
  border: 1px solid var(--border);
}

.tab-nav__item {
  padding: 7px 18px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.tab-nav__item:hover {
  color: var(--text-primary);
}

.tab-nav__item.active {
  background: var(--accent);
  color: var(--accent-ink);
}

.app-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 28px 32px 64px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.proceed-btn {
  align-self: flex-start;
}
</style>
