<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { getCourses, getVenues, putCourses, putVenues, type CourseItem, type VenueItem } from '../api'

const props = defineProps<{ grade: string }>()

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
  if (!props.grade) return
  try {
    const resp = await getCourses(props.grade)
    rows.value = resp.courses.map(toRow)
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)
watch(() => props.grade, refresh)

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
    const resp = await putCourses(props.grade, rows.value.map(toCourseItem))
    rows.value = resp.courses.map(toRow)
    notice.value = '已保存'
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- 场地容量
// 场地是物理房间，不分年级——所有年级共用同一份场地目录，跟上面按年级
// 维护的课程目录是两件独立的事，各自有各自的保存按钮。

const venueRows = ref<Array<{ name: string; capacity: string }>>([])
const venueError = ref('')
const venueNotice = ref('')
const venueSaving = ref(false)

function toVenueRow(v: VenueItem) {
  return { name: v.name, capacity: v.capacity === null ? '' : String(v.capacity) }
}

async function refreshVenues() {
  venueError.value = ''
  try {
    const resp = await getVenues()
    venueRows.value = resp.venues.map(toVenueRow)
  } catch (err) {
    venueError.value = (err as Error).message
  }
}

onMounted(refreshVenues)

async function saveVenues() {
  venueError.value = ''
  venueNotice.value = ''
  venueSaving.value = true
  try {
    const items: VenueItem[] = venueRows.value.map((r) => {
      // Vue 对 <input type="number"> 的 v-model 会自动把值转成 number（不是 string），
      // 跟 Row 类型声明的 capacity: string 不一致——这里统一转成字符串再判断，
      // 不能直接调 .trim()，否则数字输入会在这里报 "capacity.trim is not a function"。
      const raw = String(r.capacity).trim()
      return { name: r.name.trim(), capacity: raw === '' ? null : Number(raw) }
    })
    const resp = await putVenues(items)
    venueRows.value = resp.venues.map(toVenueRow)
    venueNotice.value = '已保存'
  } catch (err) {
    venueError.value = (err as Error).message
  } finally {
    venueSaving.value = false
  }
}
</script>

<template>
  <section class="card">
    <h2>课程设置（{{ grade }}）</h2>
    <p class="hint">课程名/学科系/场地/单双周，以及"占位符"（教务固定安排、系统不排课）标记。课程目录按年级分别维护。</p>

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

  <section class="card venue-card">
    <h2>场地容量</h2>
    <p class="hint">场地是物理房间，所有年级共用同一份——同一时间格能容纳几个班上课，供排课时判断是否冲突。留空表示不限制。</p>

    <table class="venue-table">
      <thead>
        <tr>
          <th>场地名</th>
          <th>容量（同时几个班）</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in venueRows" :key="i" data-test="venue-row">
          <td>{{ row.name }}</td>
          <td>
            <input data-test="venue-capacity" type="number" min="1" v-model="row.capacity" placeholder="不限" />
          </td>
        </tr>
      </tbody>
    </table>

    <div class="actions">
      <button data-test="save-venues-button" class="btn btn-primary" :disabled="venueSaving" @click="saveVenues">保存</button>
    </div>

    <p v-if="venueError" data-test="venue-error" class="alert alert-critical">{{ venueError }}</p>
    <p v-if="venueNotice" data-test="venue-notice" class="badge badge-good">{{ venueNotice }}</p>
  </section>
</template>

<style scoped>
.hint {
  color: var(--text-secondary);
  margin: 8px 0 16px;
}

.venue-card {
  margin-top: 16px;
}

.table-scroll {
  overflow-x: auto;
}

.course-table,
.venue-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.course-table th,
.venue-table th {
  text-align: left;
  padding: 8px 10px;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.course-table td,
.venue-table td {
  padding: 6px 10px;
}

.course-table tbody tr:nth-child(odd),
.venue-table tbody tr:nth-child(odd) {
  background: var(--page-bg);
}

.course-table input[type='text'],
.course-table input:not([type]),
.course-table select,
.venue-table input {
  width: 100%;
  min-width: 90px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
}

.venue-table input {
  max-width: 140px;
}

.course-table input:focus,
.course-table select:focus,
.venue-table input:focus {
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
