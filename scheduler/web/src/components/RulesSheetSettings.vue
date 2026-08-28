<script setup lang="ts">
import { ref } from 'vue'
import { parseRulesSheet, putRulesSheet, type RuleSheetParseResponse } from '../api'

const props = defineProps<{ grade: string }>()
const emit = defineEmits<{ saved: [] }>()

const preview = ref<RuleSheetParseResponse | null>(null)
const error = ref('')
const notice = ref('')
const parsing = ref(false)
const confirming = ref(false)

async function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''
  notice.value = ''
  parsing.value = true
  try {
    preview.value = await parseRulesSheet(props.grade, file)
  } catch (err) {
    error.value = (err as Error).message
    preview.value = null
  } finally {
    parsing.value = false
  }
}

async function confirm() {
  if (!preview.value) return
  confirming.value = true
  error.value = ''
  try {
    const resp = await putRulesSheet(props.grade, preview.value.rules, preview.value.teacher_facts)
    notice.value = `已写入 ${resp.rules_written} 条规则，更新 ${resp.teachers_updated} 位教师的职务/禁排信息`
    preview.value = null
    emit('saved')
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    confirming.value = false
  }
}

const columnOrder = ['不能排课节次', '固定节次', '排课要求', '备注']
</script>

<template>
  <section class="card">
    <div class="head-row">
      <div>
        <h2>排课规则（{{ grade }}）</h2>
        <p class="hint">
          上传排课说明.xlsx——只填规则文本（固定节次/不能排课节次/排课要求/备注），
          按姓名匹配「任课表」步骤已有的教师，不用再填任教班和周课时。
          不确定格式的话先下载模板参考。
        </p>
      </div>
      <div class="actions-row">
        <a class="btn btn-secondary" href="/api/config/rules-sheet/template" download>下载模板</a>
        <label class="btn btn-secondary upload-btn">
          {{ parsing ? '解析中…' : '上传排课说明.xlsx' }}
          <input data-test="rules-sheet-file" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
        </label>
      </div>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <p v-if="notice" data-test="notice" class="badge badge-good">{{ notice }}</p>

    <div v-if="preview" class="preview">
      <p class="preview-summary">
        解析出 <strong>{{ preview.rules.length }}</strong> 条规则 ·
        涉及 <strong>{{ preview.teacher_facts.length }}</strong> 位教师 ·
        AI 复核：<strong>{{ preview.ai_reviewed ? '已启用' : '未启用' }}</strong>
      </p>

      <ul v-if="preview.warnings.length" data-test="warnings" class="warning-list">
        <li v-for="(w, i) in preview.warnings" :key="i" class="alert alert-warning">{{ w }}</li>
      </ul>

      <div v-for="column in columnOrder" :key="column" class="rule-echo-group">
        <h3>{{ column }}</h3>
        <ul v-if="preview.rule_echo[column]?.length" class="rule-echo-list">
          <li v-for="(item, i) in preview.rule_echo[column]" :key="i"
              :class="{ mismatch: item.mismatch }" data-test="rule-echo-item">
            <div class="rule-line">
              <span class="rule-raw">{{ item.raw }}</span>
              <span class="rule-arrow">→</span>
              <span class="rule-parsed">{{ item.parsed }}</span>
            </div>
            <div v-if="item.mismatch" class="rule-ai-line" data-test="rule-ai-mismatch">
              需确认：AI 复核解析为「{{ item.ai_parsed }}」，与正则结果不一致
            </div>
          </li>
        </ul>
        <p v-else class="empty-hint">（无）</p>
      </div>

      <button data-test="confirm-rules-sheet-button" class="btn btn-primary confirm-btn"
              :disabled="confirming" @click="confirm">
        确认导入
      </button>
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

.actions-row {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.upload-btn {
  cursor: pointer;
}

.preview {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preview-summary {
  color: var(--text-secondary);
}

.preview-summary strong {
  color: var(--text-primary);
}

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

.empty-hint {
  color: var(--text-muted);
  font-size: 13px;
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

.rule-echo-list li.mismatch {
  background: var(--status-warning-wash);
  border: 1px solid var(--status-warning);
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

.rule-ai-line {
  margin-top: 4px;
  color: #6b4700;
  font-size: 12.5px;
}

.confirm-btn {
  align-self: flex-start;
}
</style>
