<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getGrades, solveMerged, type MergedSolveResultItem } from '../api'

const grades = ref<string[]>([])
const selected = ref<Record<string, boolean>>({})
const maxSeconds = ref(60)
const running = ref(false)
const error = ref('')
const results = ref<MergedSolveResultItem[] | null>(null)

async function load() {
  error.value = ''
  try {
    const resp = await getGrades()
    grades.value = resp.grades.map((g) => g.name)
    for (const g of grades.value) selected.value[g] = true
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(load)

const selectedGrades = () => grades.value.filter((g) => selected.value[g])

async function run() {
  error.value = ''
  results.value = null
  const picked = selectedGrades()
  if (picked.length < 2) {
    error.value = '合排至少需要选择 2 个年级'
    return
  }
  running.value = true
  try {
    const resp = await solveMerged(picked, maxSeconds.value)
    results.value = resp.results
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    running.value = false
  }
}

function statusBadgeClass(status: string): string {
  if (status === 'OPTIMAL' || status === 'FEASIBLE') return 'badge-good'
  return 'badge-critical'
}
</script>

<template>
  <section class="card">
    <h2>合排（M7）</h2>
    <p class="hint">
      联合求解选中的几个年级——同一位教师在多个年级任课时、或跨年级共用同一个场地时，
      按真实钟点区间保证不冲突，不依赖"先求解哪个年级"的顺序。每个年级需要先在下面
      「排课」里单独求解过至少一次（合排复用各年级最近一次求解留下的任课数据）。
      求解结果会分别存成每个年级的一条新求解任务，可以照常在历史记录里查看、导出。
    </p>

    <div class="grade-picks">
      <label v-for="g in grades" :key="g" class="grade-pick">
        <input type="checkbox" v-model="selected[g]" :data-test="`merged-grade-${g}`" />
        {{ g }}
      </label>
    </div>

    <div class="actions-row">
      <label class="field">
        最大求解秒数
        <input type="number" min="1" v-model.number="maxSeconds" />
      </label>
      <button data-test="run-merged-solve-button" class="btn btn-primary" :disabled="running" @click="run">
        {{ running ? '合排求解中…' : '开始合排' }}
      </button>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>

    <ul v-if="results" data-test="merged-results" class="results-list">
      <li v-for="r in results" :key="r.grade" data-test="merged-result-row">
        <span class="result-grade">{{ r.grade }}</span>
        <span class="badge" :class="statusBadgeClass(r.status)">{{ r.status }}</span>
        <span class="result-meta">{{ r.wall_time.toFixed(2) }}s · {{ r.violations }} 处违规</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.hint {
  color: var(--text-secondary);
  margin: 8px 0 16px;
  line-height: 1.6;
  max-width: 680px;
}

.grade-picks {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
}

.grade-pick {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.actions-row {
  display: flex;
  align-items: end;
  gap: 16px;
  margin-bottom: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.field input {
  width: 100px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  font-size: 13px;
}

.results-list {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.results-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--page-bg);
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.result-grade {
  font-weight: 700;
  min-width: 60px;
}

.result-meta {
  color: var(--text-muted);
  font-size: 12px;
}
</style>
