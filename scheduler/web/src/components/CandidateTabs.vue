<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { exportUrl, getCalendar } from '../api'
import ScheduleGrid from './ScheduleGrid.vue'
import TeacherScheduleGrid from './TeacherScheduleGrid.vue'
import VenueOccupancyGrid from './VenueOccupancyGrid.vue'
import IssueList from './IssueList.vue'
import AiReviewPanel from './AiReviewPanel.vue'
import SolveMonitor from './SolveMonitor.vue'

interface Candidate {
  index: number
  status: string
  wall_time: number
  objective: number | null
  stats: string
  violations: Array<{ kind: string; detail: string }>
  placements: Array<{ task_id: number; class_id: number; course: string; teacher: string; slot: number; parity: string | null }>
}

type ViewMode = 'class' | 'teacher' | 'venue' | 'monitor'

const props = defineProps<{ candidates: Candidate[]; jobId: string | null; classes: number[]; grade: string }>()

const activeIndex = ref(1)
const viewMode = ref<ViewMode>('class')

// 课表格子组件（ScheduleGrid/TeacherScheduleGrid/VenueOccupancyGrid）都支持
// 传入真实的 days/periodsPerDay，不传就默认按 9 节/天渲染——不同年级的
// 节数/星期可能不一样（比如七年级 8 节/天），这里按当前年级去取一次真实
// 作息表，取不到（还没配）就让子组件继续用默认值，不阻塞渲染。
const calendarDays = ref<string[] | undefined>(undefined)
const calendarPeriodsPerDay = ref<number | undefined>(undefined)

async function loadCalendar() {
  if (!props.grade) return
  try {
    const cal = await getCalendar(props.grade)
    calendarDays.value = cal.days
    calendarPeriodsPerDay.value = cal.periods_per_day
  } catch {
    calendarDays.value = undefined
    calendarPeriodsPerDay.value = undefined
  }
}

onMounted(loadCalendar)
watch(() => props.grade, loadCalendar)

function activate(index: number) {
  activeIndex.value = index
}
</script>

<template>
  <section v-if="candidates.length" class="card candidate-card">
    <nav class="candidate-nav">
      <button
        v-for="c in candidates"
        :key="c.index"
        data-test="candidate-tab"
        class="candidate-tab"
        :class="{ active: c.index === activeIndex }"
        @click="activate(c.index)"
      >
        方案 {{ c.index }}
        <span class="badge" :class="c.violations.length ? 'badge-warning' : 'badge-good'">
          {{ c.status }} · {{ c.violations.length }} 处违规
        </span>
      </button>
    </nav>

    <template v-for="c in candidates" :key="c.index">
      <div v-if="c.index === activeIndex" class="candidate-body">
        <nav class="view-nav">
          <button data-test="view-class" class="view-tab" :class="{ active: viewMode === 'class' }"
                  @click="viewMode = 'class'">班级课表</button>
          <button data-test="view-teacher" class="view-tab" :class="{ active: viewMode === 'teacher' }"
                  @click="viewMode = 'teacher'">教师课表</button>
          <button data-test="view-venue" class="view-tab" :class="{ active: viewMode === 'venue' }"
                  @click="viewMode = 'venue'">场地占用</button>
          <button data-test="view-monitor" class="view-tab" :class="{ active: viewMode === 'monitor' }"
                  @click="viewMode = 'monitor'">求解监控</button>
        </nav>

        <ScheduleGrid v-if="viewMode === 'class'"
                      :classes="classes" :placements="c.placements" :job-id="jobId" :candidate-index="c.index"
                      :days="calendarDays" :periods-per-day="calendarPeriodsPerDay" />
        <TeacherScheduleGrid v-else-if="viewMode === 'teacher'" :placements="c.placements"
                             :days="calendarDays" :periods-per-day="calendarPeriodsPerDay" />
        <VenueOccupancyGrid v-else-if="viewMode === 'venue'" :placements="c.placements" :grade="grade"
                            :days="calendarDays" :periods-per-day="calendarPeriodsPerDay" />
        <SolveMonitor v-else :candidates="candidates" :active-index="activeIndex" />

        <IssueList title="本方案违规明细" tone="critical" :items="c.violations" />

        <AiReviewPanel :job-id="jobId" :candidate-index="c.index" />

        <div class="export-row">
          <a v-if="jobId" data-test="export-link" class="btn btn-secondary" :href="exportUrl(jobId, c.index, false)">
            导出 Excel（简单网格版）
          </a>
          <a v-if="jobId" data-test="export-link-template" class="btn btn-secondary" :href="exportUrl(jobId, c.index, true)">
            导出 Excel（教务模板版）
          </a>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.candidate-card {
  padding: 20px;
}

.candidate-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.candidate-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px 6px 16px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-weight: 600;
  cursor: pointer;
}

.candidate-tab.active {
  border-color: var(--accent);
  color: var(--text-primary);
  background: var(--accent-wash);
}

.candidate-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.view-nav {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: var(--page-bg);
  border-radius: 999px;
  border: 1px solid var(--border);
  align-self: flex-start;
}

.view-tab {
  padding: 5px 14px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12.5px;
  cursor: pointer;
}

.view-tab.active {
  background: var(--accent);
  color: var(--accent-ink);
}

.export-row {
  display: flex;
  gap: 12px;
}
</style>
