<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  clearImports, confirmImport, deleteImport, getImportDetail, importFiles, listImports,
  type ImportPreview, type ImportSessionSummary,
} from '../api'
import HistoryList, { type HistoryRow } from './HistoryList.vue'

const emit = defineEmits<{ confirmed: [payload: { teaching_path: string; rules_path: string }] }>()

const teachingFile = ref<File | null>(null)
const rulesFile = ref<File | null>(null)
const ruleEngine = ref<'regex' | 'ai'>('regex')
const grade = ref('初三')
const preview = ref<ImportPreview | null>(null)
const error = ref('')
const confirming = ref(false)

const history = ref<ImportSessionSummary[]>([])
const historyLoading = ref(false)
const historyRows = ref<HistoryRow[]>([])

function toHistoryRows(rows: ImportSessionSummary[]): HistoryRow[] {
  return rows.map((r) => ({ id: r.token, label: r.grade, sublabel: r.created_at }))
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const resp = await listImports()
    history.value = resp.imports
    historyRows.value = toHistoryRows(resp.imports)
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    historyLoading.value = false
  }
}

async function selectHistory(token: string) {
  error.value = ''
  try {
    preview.value = await getImportDetail(token)
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function deleteHistory(token: string) {
  try {
    await deleteImport(token)
    await loadHistory()
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function clearHistory() {
  try {
    await clearImports()
    await loadHistory()
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(loadHistory)

function onTeachingFileChange(event: Event) {
  teachingFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function onRulesFileChange(event: Event) {
  rulesFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function runImport() {
  error.value = ''
  if (!teachingFile.value || !rulesFile.value) {
    error.value = '请先选择任课表和排课说明两份文件'
    return
  }
  try {
    preview.value = await importFiles(teachingFile.value, rulesFile.value, grade.value, ruleEngine.value)
    await loadHistory()
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function runConfirm() {
  if (!preview.value) return
  confirming.value = true
  try {
    const result = await confirmImport(preview.value.token)
    emit('confirmed', { teaching_path: result.teaching_path, rules_path: result.rules_path })
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    confirming.value = false
  }
}

defineExpose({ runImport })
</script>

<template>
  <section class="card">
    <h2>导入任课表与排课说明</h2>

    <HistoryList title="历史记录" :rows="historyRows" :loading="historyLoading"
                @select="selectHistory" @delete="deleteHistory" @clear="clearHistory" />

    <div class="import-form">
      <label class="field">
        任课表
        <input data-test="teaching-file" type="file" @change="onTeachingFileChange" />
      </label>
      <label class="field">
        排课说明
        <input data-test="rules-file" type="file" @change="onRulesFileChange" />
      </label>
      <label class="field">
        规则解析引擎
        <select v-model="ruleEngine">
          <option value="regex">正则（默认）</option>
          <option value="ai">AI</option>
        </select>
      </label>
      <button data-test="run-import-button" class="btn btn-primary" @click="runImport">解析</button>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>

    <div v-if="preview" class="preview">
      <p class="preview-summary">
        教师 <strong>{{ preview.teachers }}</strong> 人 · 班级 <strong>{{ preview.classes }}</strong> 个 ·
        任务 <strong>{{ preview.tasks }}</strong> 个
      </p>

      <ul v-if="preview.conflicts.length" data-test="conflicts" class="conflict-list">
        <li v-for="(c, i) in preview.conflicts" :key="i" class="alert alert-critical">
          {{ c.class_id }}班 {{ c.course }}：任课表说是「{{ c.from_teaching_table ?? '（无）' }}」，
          排课说明说是「{{ c.from_rules_sheet ?? '（无）' }}」，请先核实源文件
        </li>
      </ul>

      <div v-for="(items, column) in preview.rule_echo" :key="column" class="rule-echo-group">
        <h3>{{ column }}</h3>
        <ul class="rule-echo-list">
          <li v-for="(item, i) in items" :key="i">
            <span class="rule-raw">{{ item.raw }}</span>
            <span class="rule-arrow">→</span>
            <span class="rule-parsed">{{ item.parsed }}</span>
          </li>
        </ul>
      </div>

      <ul v-if="preview.warnings.length" class="warning-list">
        <li v-for="(w, i) in preview.warnings" :key="i" class="alert alert-warning">{{ w }}</li>
      </ul>

      <button data-test="confirm-button" class="btn btn-primary confirm-btn"
              :disabled="preview.conflicts.length > 0 || confirming"
              @click="runConfirm">
        确认导入
      </button>
    </div>
  </section>
</template>

<style scoped>
.import-form {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 16px;
  margin-top: 16px;
}

.import-form .btn {
  align-self: flex-end;
}

.preview {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.confirm-btn {
  align-self: flex-start;
}

.preview-summary {
  color: var(--text-secondary);
}

.preview-summary strong {
  color: var(--text-primary);
}

.conflict-list,
.warning-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-echo-group h3 {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.rule-echo-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rule-echo-list li {
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: var(--page-bg);
  font-size: 13px;
}

.rule-raw {
  color: var(--text-secondary);
}

.rule-arrow {
  margin: 0 6px;
  color: var(--text-muted);
}

.rule-parsed {
  color: var(--text-primary);
  font-weight: 600;
}
</style>
