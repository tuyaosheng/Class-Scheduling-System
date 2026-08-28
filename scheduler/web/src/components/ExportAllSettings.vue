<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  checkExportAll, exportAll, getGrades, listSolveJobs,
  type CrossGradeConflictItem, type SolveJobSummary,
} from '../api'

const grades = ref<string[]>([])
const jobs = ref<SolveJobSummary[]>([])
const selectedJob = ref<Record<string, string>>({})       // grade -> job_id
const selectedCandidate = ref<Record<string, number>>({}) // grade -> candidate_index
const loading = ref(false)
const checking = ref(false)
const exporting = ref(false)
const error = ref('')
const notice = ref('')
const conflicts = ref<CrossGradeConflictItem[] | null>(null)
const skippedGrades = ref<string[]>([])

function jobsFor(grade: string): SolveJobSummary[] {
  return jobs.value.filter((j) => j.grade === grade && j.candidate_count > 0)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [g, j] = await Promise.all([getGrades(), listSolveJobs()])
    grades.value = g.grades.map((x) => x.name)
    jobs.value = j.jobs
    for (const grade of grades.value) {
      const first = jobsFor(grade)[0]
      if (first && !selectedJob.value[grade]) {
        selectedJob.value[grade] = first.job_id
        selectedCandidate.value[grade] = 1
      }
    }
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(load)

const selections = computed(() =>
  grades.value
    .filter((g) => selectedJob.value[g])
    .map((g) => ({ grade: g, job_id: selectedJob.value[g], candidate_index: selectedCandidate.value[g] ?? 1 })),
)

const candidateCountFor = (grade: string): number => {
  const job = jobsFor(grade).find((j) => j.job_id === selectedJob.value[grade])
  return job?.candidate_count ?? 0
}

async function runCheck() {
  error.value = ''
  notice.value = ''
  conflicts.value = null
  checking.value = true
  try {
    const resp = await checkExportAll(selections.value)
    conflicts.value = resp.conflicts
    skippedGrades.value = resp.skipped_grades
    if (!resp.conflicts.length) notice.value = '校验通过，没有发现跨年级教师时间冲突'
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    checking.value = false
  }
}

async function runExport() {
  error.value = ''
  notice.value = ''
  exporting.value = true
  try {
    const blob = await exportAll(selections.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '全部课表.zip'
    a.click()
    URL.revokeObjectURL(url)
    notice.value = '已导出'
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <section class="card">
    <h2>导出全部课表</h2>
    <p class="hint">
      各年级独立求解，导出前统一校验一次教师跨年级时间冲突（按真实钟点区间比对，
      不同年级作息形状不同时不能只比较"第几节"）。校验不通过不能导出。
    </p>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>

    <div v-if="loading" class="empty-hint">加载中…</div>
    <div v-else-if="!grades.length" class="empty-hint">还没有配置任何年级。</div>
    <div v-else class="grade-picks">
      <div v-for="grade in grades" :key="grade" class="grade-pick" data-test="grade-pick-row">
        <span class="grade-name">{{ grade }}</span>
        <select v-if="jobsFor(grade).length" v-model="selectedJob[grade]" data-test="job-select">
          <option v-for="j in jobsFor(grade)" :key="j.job_id" :value="j.job_id">
            {{ j.created_at }} · {{ j.candidate_count }} 个候选
          </option>
        </select>
        <span v-else class="no-job-hint">没有可用的求解任务</span>
        <select v-if="jobsFor(grade).length" v-model.number="selectedCandidate[grade]" data-test="candidate-select">
          <option v-for="i in candidateCountFor(grade)" :key="i" :value="i">候选 {{ i }}</option>
        </select>
      </div>
    </div>

    <ul v-if="skippedGrades.length" class="warning-list">
      <li class="alert alert-warning">
        以下年级没有配置真实钟点表（calendars.yaml 的 clock_times），无法参与跨年级校验：
        {{ skippedGrades.join('、') }}
      </li>
    </ul>

    <ul v-if="conflicts && conflicts.length" data-test="conflicts" class="conflict-list">
      <li v-for="(c, i) in conflicts" :key="i" class="alert alert-critical">
        {{ c.teacher }} 在{{ c.day }} {{ c.start_a }}-{{ c.end_a }} 同时排了
        {{ c.grade_a }}{{ c.class_a }}班{{ c.course_a }} 和
        {{ c.grade_b }}{{ c.class_b }}班{{ c.course_b }}（{{ c.start_b }}-{{ c.end_b }}）
      </li>
    </ul>

    <div class="actions">
      <button data-test="check-button" class="btn btn-secondary" :disabled="checking || !selections.length"
              @click="runCheck">
        {{ checking ? '校验中…' : '校验' }}
      </button>
      <button data-test="export-button" class="btn btn-primary" :disabled="exporting || !selections.length"
              @click="runExport">
        {{ exporting ? '导出中…' : '导出全部' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.hint {
  color: var(--text-secondary);
  margin: 8px 0 0;
  max-width: 640px;
  line-height: 1.6;
}

.empty-hint {
  color: var(--text-muted);
  margin-top: 16px;
}

.grade-picks {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}

.grade-pick {
  display: flex;
  align-items: center;
  gap: 12px;
}

.grade-name {
  font-weight: 600;
  min-width: 72px;
}

.no-job-hint {
  color: var(--text-muted);
  font-size: 13px;
}

.warning-list,
.conflict-list {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}
</style>
