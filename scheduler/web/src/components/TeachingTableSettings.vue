<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getTeachingTable, parseTeachingTable, putTeachingTable } from '../api'

const props = defineProps<{ grade: string }>()
const emit = defineEmits<{ saved: [] }>()

const classes = ref<number[]>([])
const courses = ref<string[]>([])
const cells = ref<Record<string, string>>({})   // `${class_id}:${course}` -> 教师名
const warnings = ref<string[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)

function key(classId: number, course: string): string {
  return `${classId}:${course}`
}

function toCells(entries: Array<{ class_id: number; course: string; teacher: string }>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const e of entries) out[key(e.class_id, e.course)] = e.teacher
  return out
}

async function refresh() {
  error.value = ''
  if (!props.grade) return
  try {
    const resp = await getTeachingTable(props.grade)
    classes.value = resp.classes
    courses.value = resp.courses
    cells.value = toCells(resp.entries)
    warnings.value = resp.warnings ?? []
    dirty.value = false
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)
watch(() => props.grade, refresh)

function cellValue(classId: number, course: string): string {
  return cells.value[key(classId, course)] ?? ''
}

function onCellInput(classId: number, course: string, value: string) {
  cells.value[key(classId, course)] = value
  dirty.value = true
}

async function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''
  notice.value = ''
  loading.value = true
  try {
    const resp = await parseTeachingTable(props.grade, file)
    classes.value = resp.classes.length ? resp.classes : classes.value
    if (resp.courses.length) courses.value = resp.courses
    cells.value = toCells(resp.entries)
    warnings.value = resp.warnings ?? []
    dirty.value = true
    notice.value = '已解析，确认无误后点击"保存"写入'
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

const entryCount = computed(() => Object.values(cells.value).filter((v) => v.trim()).length)

async function save() {
  error.value = ''
  notice.value = ''
  saving.value = true
  try {
    const entries = Object.entries(cells.value)
      .filter(([, teacher]) => teacher.trim())
      .map(([k, teacher]) => {
        const [classId, course] = k.split(':')
        return { class_id: Number(classId), course, teacher: teacher.trim() }
      })
    const resp = await putTeachingTable(props.grade, entries)
    classes.value = resp.classes
    courses.value = resp.courses
    cells.value = toCells(resp.entries)
    warnings.value = resp.warnings ?? []
    dirty.value = false
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
  <section class="card">
    <div class="head-row">
      <div>
        <h2>任课表（{{ grade }}）</h2>
        <p class="hint">谁教谁的唯一来源——直接改单元格里的教师名，或整份重新上传覆盖。每门课每周几节由「课程与学科系」的课程计划统一设定，这里不用重复填。</p>
      </div>
      <label class="btn btn-secondary upload-btn">
        {{ loading ? '解析中…' : '重新上传' }}
        <input data-test="teaching-table-file" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
      </label>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <ul v-if="warnings.length" data-test="warnings" class="warning-list">
      <li v-for="(w, i) in warnings" :key="i" class="alert alert-warning">{{ w }}</li>
    </ul>

    <div v-if="!classes.length" class="empty-hint">先在「年级与班级」设置班级数量，再导入任课表。</div>
    <div v-else class="table-scroll">
      <table class="teaching-table">
        <thead>
          <tr>
            <th class="col-class">班别</th>
            <th v-for="c in courses" :key="c">{{ c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="classId in classes" :key="classId" data-test="teaching-row">
            <td class="col-class">{{ classId }} 班</td>
            <td v-for="c in courses" :key="c">
              <input
                data-test="teaching-cell"
                :value="cellValue(classId, c)"
                @input="onCellInput(classId, c, ($event.target as HTMLInputElement).value)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="actions">
      <button data-test="save-teaching-table-button" class="btn btn-primary" :disabled="saving" @click="save">保存</button>
      <span class="footer-note">已填 {{ entryCount }} 格</span>
      <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>
    </div>
  </section>
</template>

<style scoped>
.head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.hint {
  color: var(--text-secondary);
  margin: 8px 0 0;
  max-width: 560px;
  line-height: 1.6;
}

.upload-btn {
  cursor: pointer;
  flex-shrink: 0;
}

.warning-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.empty-hint {
  color: var(--text-secondary);
  margin-top: 16px;
}

.table-scroll {
  overflow: auto;
  max-height: 60vh;
  margin-top: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.teaching-table {
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  min-width: 100%;
}

.teaching-table th,
.teaching-table td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  border-right: 1px solid var(--border);
  white-space: nowrap;
  text-align: center;
}

.teaching-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
  padding: 8px 10px;
}

.col-class {
  position: sticky;
  left: 0;
  background: var(--surface-raised);
  color: var(--text-primary);
  font-weight: 600;
  z-index: 1;
}

thead .col-class {
  z-index: 3;
}

.teaching-table input {
  width: 76px;
  padding: 4px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  text-align: center;
  font-size: 12.5px;
}

.teaching-table input:hover,
.teaching-table input:focus {
  border-color: var(--border);
  background: var(--surface-raised);
  outline: none;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.footer-note {
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
