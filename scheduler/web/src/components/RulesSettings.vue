<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getRules, putRules, type RuleItem } from '../api'

const SCOPE_DIMS = ['grade', 'family', 'course', 'teacher', 'class'] as const
const SCOPE_LABEL: Record<string, string> = {
  grade: '年级', family: '学科系', course: '课程', teacher: '教师', class: '班级',
}

// 跟后端 scheduler/core/rules.py 的 _TYPE_TEMPLATE 对应——教务看不懂内部
// 英文 DSL 类型名，这里给每种类型一个中文短标签；未实现的三种（M4 软约束
// 候选项，compiler.py/verifier.py 都没做）如实标注，不隐藏也不假装生效。
const TYPE_LABEL: Record<string, string> = {
  forbid_slots: '禁排时段',
  pin_window: '锁定窗口',
  daily_min: '每天最少节数',
  daily_max: '每天最多节数',
  weekday_exact: '指定星期节数',
  consecutive: '连堂',
  spacing: '两班间隔',
  alternate_weeks: '单双周轮换',
  venue_capacity: '场地容量',
  teacher_max_run: '教师半天连堂上限',
  preferred_periods: '偏好节次（未实现）',
  avoid_after: '避免排在指定节次后（未实现）',
  teacher_balance: '教师负荷均衡（未实现）',
}

function typeLabel(type: string): string {
  return TYPE_LABEL[type] ?? type
}

interface Row {
  type: string
  scope: Record<string, string>
  paramsText: string
  mode: string
  enabled: boolean
  weight: number
  description: string
}

const rows = ref<Row[]>([])
const ruleTypes = ref<string[]>([])
const error = ref('')
const notice = ref('')
const saving = ref(false)

function scopeValueToText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return Array.isArray(value) ? value.join(',') : String(value)
}

// 作用域五维里，`class` 通常是整数班号；其余四维是字符串学科/课程/教师/年级
// 名——同一个逗号分隔的文本框，按能不能转成整数逐段猜类型，猜不出就当字符串。
function scopeTextToValue(text: string): string | number | Array<string | number> | undefined {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  const parts = trimmed.split(',').map((s) => s.trim()).filter(Boolean)
  const toPart = (s: string): string | number => (/^-?\d+$/.test(s) ? Number(s) : s)
  return parts.length > 1 ? parts.map(toPart) : toPart(parts[0])
}

function toRow(item: RuleItem): Row {
  const scope: Record<string, string> = {}
  for (const dim of SCOPE_DIMS) scope[dim] = scopeValueToText(item.scope[dim])
  return {
    type: item.type, scope, paramsText: JSON.stringify(item.params),
    mode: item.mode, enabled: item.enabled, weight: item.weight,
    description: item.description ?? '',
  }
}

function toRuleItem(row: Row): { item: RuleItem | null; error: string } {
  let params: Record<string, unknown>
  try {
    params = row.paramsText.trim() ? JSON.parse(row.paramsText) : {}
  } catch {
    return { item: null, error: `规则「${row.type}」的参数不是合法的 JSON` }
  }
  const scope: Record<string, unknown> = {}
  for (const dim of SCOPE_DIMS) {
    const value = scopeTextToValue(row.scope[dim])
    if (value !== undefined) scope[dim] = value
  }
  return {
    item: { type: row.type, scope, params, mode: row.mode, enabled: row.enabled, weight: row.weight },
    error: '',
  }
}

async function refresh() {
  error.value = ''
  try {
    const resp = await getRules()
    rows.value = resp.rules.map(toRow)
    ruleTypes.value = resp.rule_types
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)

function addRow() {
  rows.value.push({
    type: ruleTypes.value[0] ?? 'daily_min',
    scope: Object.fromEntries(SCOPE_DIMS.map((d) => [d, ''])),
    paramsText: '{}', mode: 'hard', enabled: true, weight: 0, description: '',
  })
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
}

async function save() {
  error.value = ''
  notice.value = ''
  const items: RuleItem[] = []
  for (const row of rows.value) {
    const { item, error: rowError } = toRuleItem(row)
    if (!item) {
      error.value = rowError
      return
    }
    items.push(item)
  }

  saving.value = true
  try {
    const resp = await putRules(items)
    rows.value = resp.rules.map(toRow)
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
    <h2>规则设置</h2>
    <p class="hint">
      这里只编辑手写的政策级规则（<code>rules.yaml</code>）——比如每天至少/至多几节、
      连堂、教师负荷这类全局或按学科系设定的规则。导入 Excel 生成的逐位教师禁排规则走
      「导入」流程，不在这里编辑。作用域五维留空表示不限；同一维填多个值用逗号分隔。
      每条规则下方的说明文字是上次保存时的内容，改动参数后要点"保存"才会刷新。
    </p>

    <div v-for="(row, i) in rows" :key="i" data-test="rule-row" class="rule-card">
      <div class="rule-row">
        <label class="field">
          类型
          <select data-test="rule-type" v-model="row.type">
            <option v-for="t in ruleTypes" :key="t" :value="t">{{ typeLabel(t) }}</option>
          </select>
        </label>
        <label class="field checkbox-field">
          启用
          <input data-test="rule-enabled" type="checkbox" v-model="row.enabled" />
        </label>
        <button data-test="remove-rule" class="btn btn-secondary" @click="removeRow(i)">删除</button>
      </div>

      <p v-if="row.description" data-test="rule-description" class="rule-description">
        {{ row.description }}
      </p>

      <div class="scope-row">
        <label v-for="dim in SCOPE_DIMS" :key="dim" class="field scope-field">
          {{ SCOPE_LABEL[dim] }}
          <input :data-test="`rule-scope-${dim}`" v-model="row.scope[dim]" placeholder="不限" />
        </label>
      </div>

      <label class="field params-field">
        参数（JSON）
        <textarea data-test="rule-params" v-model="row.paramsText" rows="2" />
      </label>

      <div class="mode-row">
        <label class="field">
          模式
          <select data-test="rule-mode" v-model="row.mode">
            <option value="hard">硬约束</option>
            <option value="soft">软约束</option>
          </select>
        </label>
        <label v-if="row.mode === 'soft'" class="field weight-field">
          权重（{{ row.weight }}）
          <input data-test="rule-weight" type="range" min="0" max="20" v-model.number="row.weight" />
        </label>
      </div>
    </div>

    <div class="actions">
      <button data-test="add-rule-button" class="btn btn-secondary" @click="addRow">新增规则</button>
      <button data-test="save-rules-button" class="btn btn-primary" :disabled="saving" @click="save">保存</button>
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

.rule-description {
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: var(--page-bg);
  color: var(--text-primary);
  font-size: 13px;
}

.rule-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--surface-raised);
}

.rule-row,
.scope-row,
.mode-row {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.field input,
.field select,
.field textarea {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: 13px;
  font-family: inherit;
}

.checkbox-field {
  flex-direction: row;
  align-items: center;
  gap: 6px;
}

.checkbox-field input {
  width: 16px;
  height: 16px;
}

.scope-field input {
  width: 110px;
}

.params-field textarea {
  width: 100%;
  min-width: 260px;
  resize: vertical;
}

.weight-field {
  min-width: 160px;
}

.actions {
  display: flex;
  gap: 10px;
  margin: 16px 0;
}
</style>
