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
const candidates: Candidate[] = []

async function start() {
  statusText.value = '排课中…'
  const { job_id } = await startSolve({
    grade: grade.value, count: count.value, min_diff: minDiff.value, max_seconds: maxSeconds.value,
  })
  emit('jobId', job_id)
  candidates.length = 0

  connectSolveSocket(job_id, (event) => {
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
    } else if (e.type === 'error') {
      statusText.value = '求解出错：' + (e.detail as string)
    } else if (e.type === 'done') {
      statusText.value = `完成，共 ${candidates.length} 个候选方案`
    }
  })
}
</script>

<template>
  <section>
    <h2>排课</h2>
    <label>候选数量 <input type="number" min="1" v-model.number="count" /></label>
    <label>最小差异度 <input type="number" min="1" v-model.number="minDiff" /></label>
    <button data-test="start-button" @click="start">开始排课</button>
    <p>{{ statusText }}</p>
  </section>
</template>
