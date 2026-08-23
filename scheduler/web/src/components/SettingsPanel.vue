<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getPlan, putPlan } from '../api'

const props = defineProps<{ grade: string }>()
const emit = defineEmits<{ saved: [] }>()

const plan = ref<Record<string, number>>({})
const error = ref('')
const saving = ref(false)

onMounted(async () => {
  error.value = ''
  try {
    const resp = await getPlan(props.grade)
    plan.value = resp.plan
  } catch (err) {
    error.value = (err as Error).message
  }
})

async function save() {
  error.value = ''
  saving.value = true
  try {
    await putPlan(props.grade, plan.value)
    emit('saved')
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="card">
    <h2>课程计划（{{ grade }}）</h2>
    <table class="plan-table">
      <thead>
        <tr>
          <th>课程</th>
          <th>周课时</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(hours, course) in plan" :key="course">
          <td>{{ course }}</td>
          <td>
            <input type="number" min="0" v-model.number="plan[course]" />
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <button data-test="save-button" class="btn btn-primary" :disabled="saving" @click="save">保存</button>
  </section>
</template>

<style scoped>
.plan-table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 20px;
  font-size: 13px;
}

.plan-table th {
  text-align: left;
  padding: 8px 12px;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.plan-table td {
  padding: 6px 12px;
}

.plan-table tbody tr:nth-child(odd) {
  background: var(--page-bg);
}

.plan-table input[type='number'] {
  width: 80px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  font-variant-numeric: tabular-nums;
}

.plan-table input[type='number']:focus {
  outline: 2px solid var(--accent-wash);
  border-color: var(--accent);
}
</style>
