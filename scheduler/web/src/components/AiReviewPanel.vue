<script setup lang="ts">
import { ref } from 'vue'
import { reviewCandidate, type Finding } from '../api'

const props = defineProps<{ jobId: string | null; candidateIndex: number }>()

const findings = ref<Finding[] | null>(null)
const loading = ref(false)
const error = ref('')

function scopeText(scope: Record<string, unknown>): string {
  const entries = Object.entries(scope)
  return entries.length ? entries.map(([k, v]) => `${k}=${v}`).join('、') : ''
}

async function runReview() {
  if (!props.jobId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const resp = await reviewCandidate(props.jobId, props.candidateIndex)
    findings.value = resp.findings
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="ai-review">
    <button data-test="ai-review-button" class="btn btn-secondary" :disabled="loading || !jobId" @click="runReview">
      {{ loading ? 'AI 审核中…' : 'AI 审核' }}
    </button>

    <p v-if="error" data-test="ai-review-error" class="alert alert-critical">{{ error }}</p>

    <p v-else-if="findings && findings.length === 0" class="badge badge-good">
      AI 未发现规则未覆盖的问题
    </p>

    <ul v-else-if="findings && findings.length" data-test="ai-findings" class="finding-list">
      <li v-for="(f, i) in findings" :key="i" data-test="ai-finding-item">
        <span class="badge" :class="f.severity === 'warning' ? 'badge-warning' : 'badge-neutral'">
          {{ f.severity }}
        </span>
        <span v-if="scopeText(f.scope)" class="finding-scope">[{{ scopeText(f.scope) }}]</span>
        <span class="finding-issue">{{ f.issue }}</span>
        <span v-if="f.suggestion" class="finding-suggestion">建议：{{ f.suggestion }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.ai-review {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.finding-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.finding-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  font-size: 13px;
}

.finding-scope {
  color: var(--text-secondary);
  font-size: 12px;
}

.finding-issue {
  color: var(--text-primary);
}

.finding-suggestion {
  color: var(--text-secondary);
  flex-basis: 100%;
}
</style>
