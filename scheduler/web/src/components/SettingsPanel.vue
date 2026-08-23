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
  <section>
    <h2>课程计划（{{ grade }}）</h2>
    <table>
      <tbody>
        <tr v-for="(hours, course) in plan" :key="course">
          <td>{{ course }}</td>
          <td>
            <input type="number" min="0" v-model.number="plan[course]" />
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="error" data-test="error">{{ error }}</p>
    <button data-test="save-button" :disabled="saving" @click="save">保存</button>
  </section>
</template>
