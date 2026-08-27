<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getCalendar, getGrades, putGrades, type GradeItem } from '../api'

interface Row {
  name: string
  classes: number
  calendarStatus: 'loading' | 'done' | 'missing'
}

const emit = defineEmits<{ saved: [] }>()

const rows = ref<Row[]>([])
const error = ref('')
const notice = ref('')
const saving = ref(false)
const confirmingDelete = ref<number | null>(null)

async function refreshCalendarStatus(row: Row) {
  row.calendarStatus = 'loading'
  try {
    await getCalendar(row.name)
    row.calendarStatus = 'done'
  } catch {
    row.calendarStatus = 'missing'
  }
}

async function refresh() {
  error.value = ''
  try {
    const resp = await getGrades()
    rows.value = resp.grades.map((g) => ({ name: g.name, classes: g.classes, calendarStatus: 'loading' as const }))
    await Promise.all(rows.value.map(refreshCalendarStatus))
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)

function addRow() {
  rows.value.push({ name: '', classes: 1, calendarStatus: 'missing' })
}

function askDelete(index: number) {
  confirmingDelete.value = index
}

function cancelDelete() {
  confirmingDelete.value = null
}

function confirmDelete(index: number) {
  rows.value.splice(index, 1)
  confirmingDelete.value = null
}

function inc(row: Row) {
  row.classes += 1
}

function dec(row: Row) {
  if (row.classes > 1) row.classes -= 1
}

async function save() {
  error.value = ''
  notice.value = ''
  const items: GradeItem[] = rows.value.map((r) => ({ name: r.name.trim(), classes: r.classes }))
  if (items.some((g) => !g.name)) {
    error.value = '年级名不能为空'
    return
  }
  saving.value = true
  try {
    const resp = await putGrades(items)
    rows.value = resp.grades.map((g) => ({ name: g.name, classes: g.classes, calendarStatus: 'loading' as const }))
    await Promise.all(rows.value.map(refreshCalendarStatus))
    notice.value = '已保存'
    emit('saved')
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="grades-settings">
    <div class="step-eyebrow">第 1 步 · 共 9 步</div>
    <h1 class="page-title">年级与班级</h1>
    <p class="page-sub">先建立年级和每个年级的班级数量——后面的作息、课程、任课表、排课规则都按年级分别配置，年级名称任意，数量不限。</p>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>

    <div class="grade-list">
      <div v-for="(row, i) in rows" :key="i" data-test="grade-row" class="grade-card">
        <div class="grade-card-avatar">{{ row.name ? row.name.slice(0, 2) : '?' }}</div>
        <div class="grade-card-body">
          <input data-test="grade-name" class="grade-name-input" v-model="row.name" placeholder="年级名称" />
          <div class="grade-card-meta">
            <div class="stepper">
              <button data-test="grade-classes-dec" @click="dec(row)">−</button>
              <span class="val" data-test="grade-classes-val">{{ row.classes }}</span>
              <button data-test="grade-classes-inc" @click="inc(row)">+</button>
            </div>
            <span>个班级</span>
            <span class="dot-sep"></span>
            <span class="status-chip" :class="row.calendarStatus === 'done' ? 'good' : 'warn'" data-test="calendar-status">
              {{ row.calendarStatus === 'loading' ? '检查中…' : row.calendarStatus === 'done' ? '作息已导入' : '作息未导入' }}
            </span>
          </div>
        </div>
        <div class="grade-card-actions">
          <template v-if="confirmingDelete === i">
            <span class="confirm-text">确定删除「{{ row.name || '(未命名)' }}」？</span>
            <button data-test="confirm-delete" class="btn btn-secondary" @click="confirmDelete(i)">确定</button>
            <button class="btn btn-ghost" @click="cancelDelete">取消</button>
          </template>
          <button v-else data-test="remove-grade" class="btn btn-ghost" @click="askDelete(i)">删除</button>
        </div>
      </div>

      <button data-test="add-grade-button" class="add-grade-card" @click="addRow">
        <svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        新增年级
      </button>
    </div>

    <div class="footer-actions">
      <button data-test="save-grades-button" class="btn btn-primary btn-lg" :disabled="saving" @click="save">保存</button>
      <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>
    </div>
  </section>
</template>

<style scoped>
.grades-settings { max-width: 760px; }
.step-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--accent); }
.page-title { font-size: 26px; font-weight: 700; letter-spacing: -0.01em; margin-top: 6px; }
.page-sub { font-size: 14px; color: var(--text-secondary); margin-top: 8px; line-height: 1.6; max-width: 560px; }

.grade-list { display: flex; flex-direction: column; gap: 12px; margin-top: 24px; }

.grade-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card); padding: 18px 22px; display: flex; align-items: center; gap: 18px;
}
.grade-card-avatar {
  width: 44px; height: 44px; border-radius: var(--radius-md); background: var(--accent-wash);
  color: var(--accent); display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700; flex-shrink: 0;
}
.grade-card-body { flex: 1; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.grade-name-input {
  font-size: 15.5px; font-weight: 700; border: 1px solid transparent; background: transparent;
  padding: 2px 4px; border-radius: var(--radius-sm); width: fit-content; min-width: 80px; color: var(--text-primary);
}
.grade-name-input:hover, .grade-name-input:focus { border-color: var(--border); background: var(--surface-raised); outline: none; }
.grade-card-meta { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--text-secondary); }
.dot-sep { width: 3px; height: 3px; border-radius: 999px; background: var(--border); }

.stepper { display: flex; align-items: center; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.stepper button { width: 24px; height: 24px; border: none; background: var(--surface-raised); color: var(--text-secondary); font-size: 15px; cursor: pointer; }
.stepper .val { width: 32px; text-align: center; font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }

.status-chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
.status-chip.good { background: var(--status-good-wash); color: var(--status-good); }
.status-chip.warn { background: var(--status-warning-wash); color: #8a5c00; }

.grade-card-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.confirm-text { font-size: 12.5px; color: var(--text-secondary); white-space: nowrap; }

.add-grade-card {
  border: 1.5px dashed var(--border); border-radius: var(--radius-lg); padding: 16px; background: transparent;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  color: var(--text-muted); font-size: 13.5px; font-weight: 600; cursor: pointer;
}

.footer-actions { display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding-top: 20px; }
.btn-lg { padding: 12px 22px; font-size: 14px; }
.icon { display: block; }
</style>
