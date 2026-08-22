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
  <section v-if="candidates.length">
    <nav>
      <button
        v-for="c in candidates"
        :key="c.index"
        data-test="candidate-tab"
        :class="{ active: c.index === activeIndex }"
        @click="activate(c.index)"
      >
        方案 {{ c.index }}（{{ c.status }}，{{ c.violations.length }} 处违规）
      </button>
    </nav>

    <template v-for="c in candidates" :key="c.index">
      <div v-if="c.index === activeIndex">
        <ScheduleGrid :classes="classes" :placements="c.placements" />
        <a v-if="jobId" data-test="export-link" :href="exportUrl(jobId, c.index, false)">
          导出 Excel（简单网格版）
        </a>
        <a v-if="jobId" data-test="export-link-template" :href="exportUrl(jobId, c.index, true)">
          导出 Excel（教务模板版）
        </a>
      </div>
    </template>
  </section>
</template>
