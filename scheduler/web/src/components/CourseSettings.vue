<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getCourses, putCourses, type CourseItem } from '../api'

interface Row {
  name: string
  family: string
  venue: string
  alternate: string
  external: boolean
}

const rows = ref<Row[]>([])
const error = ref('')
const notice = ref('')
const saving = ref(false)

function toRow(c: CourseItem): Row {
  return { name: c.name, family: c.family, venue: c.venue ?? '', alternate: c.alternate ?? '', external: c.external }
}

function toCourseItem(r: Row): CourseItem {
  return {
    name: r.name.trim(),
    family: r.family.trim(),
    venue: r.venue.trim() || null,
    alternate: r.alternate || null,
    external: r.external,
  }
}

async function refresh() {
  error.value = ''
  try {
    const resp = await getCourses()
    rows.value = resp.courses.map(toRow)
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)

function addRow() {
  rows.value.push({ name: '', family: '', venue: '', alternate: '', external: false })
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
}

async function save() {
  error.value = ''
  notice.value = ''
  saving.value = true
  try {
    const resp = await putCourses(rows.value.map(toCourseItem))
    rows.value = resp.courses.map(toRow)
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
    <h2>课程设置</h2>
    <p class="hint">课程名/学科系/场地/单双周，以及"占位符"（教务固定安排、系统不排课）标记。</p>

    <div class="table-scroll">
      <table class="course-table">
        <thead>
          <tr>
            <th>课程名</th>
            <th>学科系</th>
            <th>场地</th>
            <th>单双周</th>
            <th>占位符</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i" data-test="course-row">
            <td><input data-test="course-name" v-model="row.name" /></td>
            <td><input data-test="course-family" v-model="row.family" /></td>
            <td><input data-test="course-venue" v-model="row.venue" placeholder="不限" /></td>
            <td>
              <select data-test="course-alternate" v-model="row.alternate">
                <option value="">无</option>
                <option value="单周">单周</option>
                <option value="双周">双周</option>
              </select>
            </td>
            <td class="center">
              <input data-test="course-external" type="checkbox" v-model="row.external" />
            </td>
            <td>
              <button data-test="remove-course" class="btn btn-secondary" @click="removeRow(i)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="actions">
      <button data-test="add-course-button" class="btn btn-secondary" @click="addRow">新增课程</button>
      <button data-test="save-courses-button" class="btn btn-primary" :disabled="saving" @click="save">保存</button>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>
  </section>
</template>

<style scoped>
.hint {
  color: var(--text-secondary);
  margin: 8px 0 16px;
}

.table-scroll {
  overflow-x: auto;
}

.course-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.course-table th {
  text-align: left;
  padding: 8px 10px;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.course-table td {
  padding: 6px 10px;
}

.course-table tbody tr:nth-child(odd) {
  background: var(--page-bg);
}

.course-table input[type='text'],
.course-table input:not([type]),
.course-table select {
  width: 100%;
  min-width: 90px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
}

.course-table input:focus,
.course-table select:focus {
  outline: 2px solid var(--accent-wash);
  border-color: var(--accent);
}

.course-table .center {
  text-align: center;
}

.course-table input[type='checkbox'] {
  width: 16px;
  height: 16px;
}

.actions {
  display: flex;
  gap: 10px;
  margin: 16px 0;
}
</style>
