<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getConfigStatus } from './api'
import ImportPanel from './components/ImportPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import SolvePanel from './components/SolvePanel.vue'
import CandidateTabs from './components/CandidateTabs.vue'

type Stage = 'idle' | 'needs_import' | 'configuring' | 'ready'

interface Candidate {
  index: number
  status: string
  wall_time: number
  violations: unknown[]
  placements: Array<{ class_id: number; course: string; slot: number; parity: string | null }>
}

const stage = ref<Stage>('idle')
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
  <main>
    <h1>排课系统</h1>

    <p v-if="error" data-test="error">{{ error }}</p>

    <ImportPanel v-if="stage === 'needs_import'" @confirmed="onImportConfirmed" />

    <template v-if="stage === 'configuring'">
      <SettingsPanel :grade="grade" />
      <button data-test="proceed-to-solve" @click="proceedToSolve">前往排课</button>
    </template>

    <template v-if="stage === 'ready'">
      <SolvePanel @job-id="onJobId" @candidates="onCandidates" />
      <CandidateTabs :candidates="candidates" :job-id="jobId" :classes="classes" />
    </template>
  </main>
</template>
