<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getConfigStatus, getGrades } from './api'
import AiSettings from './components/AiSettings.vue'
import AlternatePairsSettings from './components/AlternatePairsSettings.vue'
import AppSidebar, { type StepDef } from './components/AppSidebar.vue'
import CandidateTabs from './components/CandidateTabs.vue'
import ComingSoonPanel from './components/ComingSoonPanel.vue'
import CourseSettings from './components/CourseSettings.vue'
import GradesSettings from './components/GradesSettings.vue'
import CalendarSettings from './components/CalendarSettings.vue'
import ImportPanel from './components/ImportPanel.vue'
import RulesSettings from './components/RulesSettings.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import SolvePanel from './components/SolvePanel.vue'
import TeachingTableSettings from './components/TeachingTableSettings.vue'

interface Candidate {
  index: number
  status: string
  wall_time: number
  objective: number | null
  stats: string
  violations: Array<{ kind: string; detail: string }>
  placements: Array<{ task_id: number; class_id: number; course: string; teacher: string; slot: number; parity: string | null }>
}

const STEPS: StepDef[] = [
  { id: 1, label: '年级与班级' },
  { id: 2, label: '作息时间' },
  { id: 3, label: '课程与学科系' },
  { id: 4, label: '单双周设置' },
  { id: 5, label: '任课表' },
  { id: 6, label: '排课规则' },
  { id: 7, label: '排课与调整' },
  { id: 8, label: 'AI 审核' },
  { id: 9, label: '导出课表' },
]

const currentStep = ref(1)
const showingSettings = ref(false)
const grades = ref<string[]>([])
const activeGrade = ref('')
const configReady = ref(false)
const error = ref('')

const classes = ref<number[]>([])
const candidates = ref<Candidate[]>([])
const jobId = ref<string | null>(null)

const doneSteps = computed(() => {
  const done: number[] = []
  if (grades.value.length) done.push(1)
  if (configReady.value) done.push(5)
  return done
})

async function loadGrades() {
  try {
    const resp = await getGrades()
    grades.value = resp.grades.map((g) => g.name)
    if (!activeGrade.value || !grades.value.includes(activeGrade.value)) {
      activeGrade.value = grades.value[0] ?? ''
    }
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(async () => {
  error.value = ''
  await loadGrades()
  try {
    const status = await getConfigStatus()
    configReady.value = status.ready
    if (status.ready && status.grade) activeGrade.value = status.grade
  } catch (err) {
    // 后端起不来 / 网络错误：不能让 await 无人接住，否则页面永远停在空白状态——
    // 把原因显示出来，而不是猜不出到底发生了什么（见 finding I1）。
    error.value = (err as Error).message
  }
})

function selectStep(id: number) {
  currentStep.value = id
  showingSettings.value = false
}

function selectGrade(name: string) {
  activeGrade.value = name
}

function openSettings() {
  showingSettings.value = true
}

function onImportConfirmed() {
  configReady.value = true
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
    <AppSidebar
      :steps="STEPS"
      :current-step="currentStep"
      :done-steps="doneSteps"
      :grades="grades"
      :active-grade="activeGrade"
      :showing-settings="showingSettings"
      @select-step="selectStep"
      @select-grade="selectGrade"
      @add-grade="selectStep(1)"
      @open-settings="openSettings"
    />

    <main class="app-content">
      <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>

      <AiSettings v-if="showingSettings" />

      <template v-else>
        <GradesSettings v-if="currentStep === 1" @saved="loadGrades" />

        <CalendarSettings v-else-if="currentStep === 2" />

        <div v-else-if="currentStep === 3" class="step-block">
          <div class="step-eyebrow">第 3 步 · 共 9 步</div>
          <CourseSettings v-if="activeGrade" :grade="activeGrade" />
          <SettingsPanel v-if="activeGrade" :grade="activeGrade" />
        </div>

        <div v-else-if="currentStep === 4" class="step-block">
          <div class="step-eyebrow">第 4 步 · 共 9 步</div>
          <AlternatePairsSettings v-if="activeGrade" :grade="activeGrade" />
        </div>

        <div v-else-if="currentStep === 5" class="step-block wide">
          <div class="step-eyebrow">第 5 步 · 共 9 步</div>
          <TeachingTableSettings v-if="activeGrade" :grade="activeGrade" @saved="onImportConfirmed" />
        </div>

        <div v-else-if="currentStep === 6" class="step-block">
          <div class="step-eyebrow">第 6 步 · 共 9 步</div>
          <h1 class="page-title">排课规则</h1>
          <p class="alert alert-warning">这是临时的开发视图，规则类型仍是内部英文名——后续会换成挑不懂 DSL 也能用的界面。大部分规则应由排课说明导入自动生成，这里只用来手调少数政策性规则（比如教师半天连堂上限）。</p>
          <RulesSettings />
          <p class="alert alert-warning">下面这个"两份 Excel 一次性导入"是旧版流程的临时保留——它同时处理任课信息和规则解析，跟上面新的「任课表」步骤有重叠。排课说明.xlsx 的规则解析还没独立出一个专门步骤之前，需要完整规则（教师禁排等）时仍要用它；只想改任课表本身，用第 5 步就够。</p>
          <ImportPanel @confirmed="onImportConfirmed" />
        </div>

        <div v-else-if="currentStep === 7" class="step-block">
          <div class="step-eyebrow">第 7 步 · 共 9 步</div>
          <h1 class="page-title">排课与调整</h1>
          <SolvePanel @job-id="onJobId" @candidates="onCandidates" />
          <CandidateTabs :candidates="candidates" :job-id="jobId" :classes="classes" :grade="activeGrade" />
        </div>

        <ComingSoonPanel v-else-if="currentStep === 8"
          step-eyebrow="第 8 步 · 共 9 步" title="AI 审核"
          body="跨年级统一审核三个年级的课表还没做。现在可以在「排课与调整」页面对单个候选方案单独发起 AI 审核。" />

        <ComingSoonPanel v-else-if="currentStep === 9"
          step-eyebrow="第 9 步 · 共 9 步" title="导出课表"
          body="导出前的跨年级统一校验、以及一次性导出全部年级课表还没做。现在可以在「排课与调整」页面为单个年级单独导出。" />
      </template>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--page-bg);
}

.app-content {
  flex: 1;
  padding: 44px 56px 56px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-block {
  max-width: 760px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-block.wide {
  max-width: none;
}

.step-eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--accent);
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin-top: -12px;
}
</style>
