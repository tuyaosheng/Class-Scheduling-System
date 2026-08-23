<script setup lang="ts">
import { ref } from 'vue'
import { exportUrl } from '../api'
import ScheduleGrid from './ScheduleGrid.vue'

interface Candidate {
  index: number
  status: string
  wall_time: number
  violations: unknown[]
  placements: Array<{ class_id: number; course: string; slot: number; parity: string | null }>
}

const props = defineProps<{ candidates: Candidate[]; jobId: string | null; classes: number[] }>()

const activeIndex = ref(1)

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
        <ScheduleGrid :classes="classes" :placements="c.placements" />
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

.export-row {
  display: flex;
  gap: 12px;
}
</style>
