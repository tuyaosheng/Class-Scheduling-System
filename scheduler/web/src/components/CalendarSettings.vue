<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  getCalendar, getGrades, parseCalendarWorkbook, putCalendar,
  type CalendarItem, type ParsedCalendarSheet,
} from '../api'

const grades = ref<string[]>([])
const currentByGrade = ref<Record<string, CalendarItem | null>>({})
const error = ref('')
const notice = ref('')

// ---- 手动编辑：不想每次改一点作息就重新做一份 Excel 上传，直接在页面上改。
const editingGrade = ref<string | null>(null)
const editDays = ref<string[]>(['周一', '周二', '周三', '周四', '周五'])
const editPeriodsPerDay = ref(9)
const editMiddayBreakAfter = ref(5)
const editClockTimes = ref<Array<[string, string]>>([])
const editSaving = ref(false)
const editError = ref('')

function syncClockTimesLength() {
  const n = editPeriodsPerDay.value
  const current = editClockTimes.value
  if (current.length === n) return
  if (current.length < n) {
    const extra: Array<[string, string]> = Array.from({ length: n - current.length }, () => ['', ''])
    editClockTimes.value = [...current, ...extra]
  } else {
    editClockTimes.value = current.slice(0, n)
  }
}

function startEdit(grade: string) {
  editingGrade.value = grade
  editError.value = ''
  const existing = currentByGrade.value[grade]
  if (existing) {
    editDays.value = [...existing.days]
    editPeriodsPerDay.value = existing.periods_per_day
    editMiddayBreakAfter.value = existing.midday_break_after
    editClockTimes.value = existing.clock_times.map((t) => [...t] as [string, string])
  } else {
    editDays.value = ['周一', '周二', '周三', '周四', '周五']
    editPeriodsPerDay.value = 9
    editMiddayBreakAfter.value = 5
    editClockTimes.value = Array.from({ length: 9 }, () => ['', ''] as [string, string])
  }
}

function cancelEdit() {
  editingGrade.value = null
  editError.value = ''
}

async function saveEdit() {
  if (!editingGrade.value) return
  editError.value = ''
  if (editMiddayBreakAfter.value < 1 || editMiddayBreakAfter.value >= editPeriodsPerDay.value) {
    editError.value = '午休边界必须在 1 到"每天节数-1"之间'
    return
  }
  editSaving.value = true
  try {
    await putCalendar(editingGrade.value, {
      days: editDays.value,
      periods_per_day: editPeriodsPerDay.value,
      midday_break_after: editMiddayBreakAfter.value,
      clock_times: editClockTimes.value,
    })
    notice.value = `已保存「${editingGrade.value}」的作息`
    editingGrade.value = null
    await refresh()
  } catch (err) {
    editError.value = (err as Error).message
  } finally {
    editSaving.value = false
  }
}

const editPeriodNumbers = computed(() => Array.from({ length: editPeriodsPerDay.value }, (_, i) => i + 1))

watch(editPeriodsPerDay, syncClockTimesLength)

const parsedSheets = ref<ParsedCalendarSheet[]>([])
const mapping = ref<Record<string, string>>({})   // sheet_name -> grade
const parsing = ref(false)
const confirming = ref(false)

async function refresh() {
  error.value = ''
  try {
    const resp = await getGrades()
    grades.value = resp.grades.map((g) => g.name)
    const entries = await Promise.all(grades.value.map(async (g) => {
      try {
        return [g, await getCalendar(g)] as const
      } catch {
        return [g, null] as const
      }
    }))
    currentByGrade.value = Object.fromEntries(entries)
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)

async function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''
  notice.value = ''
  parsing.value = true
  try {
    const resp = await parseCalendarWorkbook(file)
    parsedSheets.value = resp.sheets
    mapping.value = {}
    for (const sheet of resp.sheets) {
      const guess = grades.value.find((g) => g === sheet.sheet_name)
      if (guess) mapping.value[sheet.sheet_name] = guess
    }
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    parsing.value = false
  }
}

function timeRangeText(sheet: ParsedCalendarSheet): string {
  const first = sheet.clock_times[0]
  const last = sheet.clock_times[sheet.clock_times.length - 1]
  return first && last ? `${first[0]} ～ ${last[1]}` : ''
}

async function confirmSheet(sheet: ParsedCalendarSheet) {
  const grade = mapping.value[sheet.sheet_name]
  if (!grade) {
    error.value = '请先选择这个 sheet 对应哪个年级'
    return
  }
  error.value = ''
  confirming.value = true
  try {
    await putCalendar(grade, {
      periods_per_day: sheet.periods_per_day,
      midday_break_after: sheet.midday_break_after,
      clock_times: sheet.clock_times,
    })
    notice.value = `已为「${grade}」写入作息（${sheet.sheet_name}）`
    parsedSheets.value = parsedSheets.value.filter((s) => s.sheet_name !== sheet.sheet_name)
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    confirming.value = false
  }
}
</script>

<template>
  <section class="calendar-settings">
    <div class="step-eyebrow">第 2 步 · 共 9 步</div>
    <h1 class="page-title">作息时间</h1>
    <p class="page-sub">批量导入「作息表模板.xlsx」——每个 sheet 是一个年级的作息，节次数、上下课钟点、午休边界都会自动识别。sheet 名不用跟年级名完全一致，导入时手动选对应关系。</p>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>

    <div class="upload-row">
      <label class="btn btn-primary">
        {{ parsing ? '解析中…' : '上传作息表' }}
        <input data-test="calendar-file" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
      </label>
    </div>

    <div v-if="parsedSheets.length" class="sheet-list">
      <div v-for="sheet in parsedSheets" :key="sheet.sheet_name" data-test="parsed-sheet" class="sheet-card">
        <div class="sheet-info">
          <div class="sheet-name">{{ sheet.sheet_name }}</div>
          <div class="sheet-meta">
            每天 {{ sheet.periods_per_day }} 节 · 午休在第 {{ sheet.midday_break_after }} 节后 · {{ timeRangeText(sheet) }}
          </div>
        </div>
        <select data-test="sheet-grade-select" v-model="mapping[sheet.sheet_name]">
          <option value="">选择对应年级…</option>
          <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
        </select>
        <button data-test="confirm-sheet" class="btn btn-secondary" :disabled="confirming" @click="confirmSheet(sheet)">写入</button>
      </div>
    </div>

    <div class="current-list">
      <h2>各年级当前作息</h2>
      <div v-for="g in grades" :key="g" data-test="current-calendar-row" class="current-row">
        <span class="current-grade">{{ g }}</span>
        <span v-if="currentByGrade[g]" class="status-chip good">
          每天 {{ currentByGrade[g]!.periods_per_day }} 节 · 午休在第 {{ currentByGrade[g]!.midday_break_after }} 节后
        </span>
        <span v-else class="status-chip warn">未导入</span>
        <button data-test="edit-calendar-button" class="btn btn-secondary edit-btn" @click="startEdit(g)">
          {{ currentByGrade[g] ? '手动编辑' : '手动新建' }}
        </button>
      </div>
    </div>

    <div v-if="editingGrade" class="edit-panel" data-test="calendar-edit-panel">
      <h2>编辑「{{ editingGrade }}」的作息</h2>
      <p v-if="editError" data-test="edit-error" class="alert alert-critical">{{ editError }}</p>

      <div class="edit-row">
        <label class="field">
          每天节数
          <input data-test="edit-periods-per-day" type="number" min="1" max="20" v-model.number="editPeriodsPerDay" />
        </label>
        <label class="field">
          午休在第几节后
          <input data-test="edit-midday-break" type="number" min="1" v-model.number="editMiddayBreakAfter" />
        </label>
      </div>

      <table class="clock-table">
        <thead>
          <tr><th>节次</th><th>上课时间</th><th>下课时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="n in editPeriodNumbers" :key="n" data-test="clock-time-row">
            <td>{{ n }}{{ n === editMiddayBreakAfter ? '（午休前最后一节）' : '' }}</td>
            <td><input data-test="clock-time-start" v-model="editClockTimes[n - 1][0]" placeholder="08:00" /></td>
            <td><input data-test="clock-time-end" v-model="editClockTimes[n - 1][1]" placeholder="08:45" /></td>
          </tr>
        </tbody>
      </table>

      <div class="edit-actions">
        <button data-test="save-calendar-edit" class="btn btn-primary" :disabled="editSaving" @click="saveEdit">
          保存
        </button>
        <button data-test="cancel-calendar-edit" class="btn btn-secondary" @click="cancelEdit">取消</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.calendar-settings { max-width: 760px; }
.step-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--accent); }
.page-title { font-size: 26px; font-weight: 700; letter-spacing: -0.01em; margin-top: 6px; }
.page-sub { font-size: 14px; color: var(--text-secondary); margin-top: 8px; line-height: 1.6; max-width: 560px; }

.upload-row { margin-top: 20px; }
.upload-row .btn { cursor: pointer; }

.sheet-list { display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }
.sheet-card {
  display: flex; align-items: center; gap: 14px; padding: 14px 18px;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
}
.sheet-info { flex: 1; }
.sheet-name { font-weight: 700; font-size: 14px; }
.sheet-meta { font-size: 12px; color: var(--text-secondary); margin-top: 3px; }
.sheet-card select { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-raised); font-size: 13px; }

.current-list { margin-top: 32px; }
.current-list h2 { font-size: 13px; color: var(--text-secondary); margin-bottom: 10px; }
.current-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.current-grade { font-weight: 700; min-width: 60px; }
.status-chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
.status-chip.good { background: var(--status-good-wash); color: var(--status-good); }
.status-chip.warn { background: var(--status-warning-wash); color: #8a5c00; }
.edit-btn { margin-left: auto; }

.edit-panel {
  margin-top: 28px; padding: 18px 20px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
}
.edit-panel h2 { font-size: 15px; margin-bottom: 12px; }

.edit-row { display: flex; gap: 16px; margin-bottom: 16px; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.field input {
  padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-raised); font-size: 13px; width: 140px;
}

.clock-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px; }
.clock-table th { text-align: left; color: var(--text-secondary); font-size: 12px; padding: 4px 8px; }
.clock-table td { padding: 4px 8px; }
.clock-table input {
  width: 90px; padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-raised); font-size: 13px;
}

.edit-actions { display: flex; gap: 10px; }
</style>
