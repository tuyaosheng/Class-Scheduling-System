<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  getAlternatePairs, getCourses, putAlternatePairs,
  type AlternatePairItem, type CourseItem,
} from '../api'

const props = defineProps<{ grade: string }>()

const courses = ref<CourseItem[]>([])
const readonlyPairs = ref<AlternatePairItem[]>([])
const rows = ref<AlternatePairItem[]>([])
const error = ref('')
const notice = ref('')
const saving = ref(false)

async function refresh() {
  error.value = ''
  if (!props.grade) return
  try {
    const [coursesResp, pairsResp] = await Promise.all([
      getCourses(props.grade), getAlternatePairs(props.grade),
    ])
    courses.value = coursesResp.courses
    readonlyPairs.value = pairsResp.pairs.filter((p) => !p.editable)
    rows.value = pairsResp.pairs.filter((p) => p.editable)
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)
watch(() => props.grade, refresh)

function addRow() {
  rows.value.push({ family: '', single_course: '', double_course: '', editable: true })
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
}

async function save() {
  error.value = ''
  notice.value = ''
  saving.value = true
  try {
    const resp = await putAlternatePairs(props.grade, rows.value.map((r) => ({
      family: r.family.trim(), single_course: r.single_course, double_course: r.double_course, editable: true,
    })))
    readonlyPairs.value = resp.pairs.filter((p) => !p.editable)
    rows.value = resp.pairs.filter((p) => p.editable)
    notice.value = '已保存'
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="card">
    <h2>单双周设置（{{ grade }}）</h2>
    <p class="hint">选两门课合并为一门单双周课程——单周上其中一门，双周上另一门，两门课占同一个时间格。每个班按班号奇偶自动错开，两位老师的课时负荷都是均匀的。</p>

    <div v-if="readonlyPairs.length" class="readonly-list">
      <div v-for="(p, i) in readonlyPairs" :key="i" data-test="readonly-pair" class="pair-row readonly">
        <span class="badge badge-neutral">来自导入</span>
        <span class="pair-text">{{ p.family }}：单周 {{ p.single_course }} / 双周 {{ p.double_course }}</span>
      </div>
    </div>

    <div class="editable-list">
      <div v-for="(row, i) in rows" :key="i" data-test="pair-row" class="pair-row">
        <input data-test="pair-family" v-model="row.family" placeholder="合并后的学科系名" class="family-input" />
        <select data-test="pair-single" v-model="row.single_course">
          <option value="">单周课程…</option>
          <option v-for="c in courses" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <select data-test="pair-double" v-model="row.double_course">
          <option value="">双周课程…</option>
          <option v-for="c in courses" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <button data-test="remove-pair" class="btn btn-ghost" @click="removeRow(i)">删除</button>
      </div>
    </div>

    <div class="actions">
      <button data-test="add-pair-button" class="btn btn-secondary" @click="addRow">新增配对</button>
      <button data-test="save-pairs-button" class="btn btn-primary" :disabled="saving" @click="save">保存</button>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>
  </section>
</template>

<style scoped>
.hint {
  color: var(--text-secondary);
  margin: 8px 0 16px;
  line-height: 1.6;
}

.readonly-list, .editable-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.pair-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--page-bg);
}

.pair-row.readonly {
  color: var(--text-secondary);
}

.pair-text {
  font-size: 13px;
}

.family-input {
  width: 140px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
}

.pair-row select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  min-width: 130px;
}

.actions {
  display: flex;
  gap: 10px;
  margin: 16px 0;
}
</style>
