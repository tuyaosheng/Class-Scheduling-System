<script setup lang="ts">
import { ref } from 'vue'
import { confirmImport, importFiles, type ImportPreview } from '../api'

const emit = defineEmits<{ confirmed: [payload: { teaching_path: string; rules_path: string }] }>()

const teachingFile = ref<File | null>(null)
const rulesFile = ref<File | null>(null)
const ruleEngine = ref<'regex' | 'ai'>('regex')
const grade = ref('初三')
const preview = ref<ImportPreview | null>(null)
const error = ref('')
const confirming = ref(false)

function onTeachingFileChange(event: Event) {
  teachingFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function onRulesFileChange(event: Event) {
  rulesFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function runImport() {
  error.value = ''
  try {
    preview.value = await importFiles(
      teachingFile.value as File, rulesFile.value as File, grade.value, ruleEngine.value,
    )
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
  <section>
    <h2>导入任课表与排课说明</h2>
    <label>任课表 <input data-test="teaching-file" type="file" @change="onTeachingFileChange" /></label>
    <label>排课说明 <input data-test="rules-file" type="file" @change="onRulesFileChange" /></label>
    <label>
      规则解析引擎
      <select v-model="ruleEngine">
        <option value="regex">正则（默认）</option>
        <option value="ai">AI</option>
      </select>
    </label>
    <button data-test="run-import-button" @click="runImport">解析</button>

    <p v-if="error" data-test="error">{{ error }}</p>

    <div v-if="preview">
      <p>教师 {{ preview.teachers }} 人 · 班级 {{ preview.classes }} 个 · 任务 {{ preview.tasks }} 个</p>

      <ul v-if="preview.conflicts.length" data-test="conflicts">
        <li v-for="(c, i) in preview.conflicts" :key="i">
          {{ c.class_id }}班 {{ c.course }}：任课表说是「{{ c.from_teaching_table ?? '（无）' }}」，
          排课说明说是「{{ c.from_rules_sheet ?? '（无）' }}」，请先核实源文件
        </li>
      </ul>

      <div v-for="(items, column) in preview.rule_echo" :key="column">
        <h3>{{ column }}</h3>
        <ul>
          <li v-for="(item, i) in items" :key="i">{{ item.raw }} → {{ item.parsed }}</li>
        </ul>
      </div>

      <ul v-if="preview.warnings.length">
        <li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li>
      </ul>

      <button data-test="confirm-button" :disabled="preview.conflicts.length > 0 || confirming"
              @click="runConfirm">
        确认导入
      </button>
    </div>
  </section>
</template>
