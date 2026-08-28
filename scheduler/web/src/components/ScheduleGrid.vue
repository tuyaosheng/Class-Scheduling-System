<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { adjustCandidate } from '../api'

interface Placement {
  task_id: number
  class_id: number
  course: string
  slot: number
  parity: string | null
}

const props = defineProps<{
  classes: number[]
  placements: Placement[]
  jobId?: string | null
  candidateIndex?: number | null
  days?: string[]
  periodsPerDay?: number
}>()

// 组件本身不再硬编码日历形状——按年级参数化之后，不同年级每天节数可能
// 不一样。调用方目前还没把真实日历数据一路传下来（那是另一件事），先给
// 一个跟旧硬编码值一致的默认值，保持行为不变，等调用方接入日历数据后
// 传真实的 days/periodsPerDay 进来就会自动生效。
const DAYS = computed(() => props.days ?? ['周一', '周二', '周三', '周四', '周五'])
const PERIODS_PER_DAY = computed(() => props.periodsPerDay ?? 9)
const N_SLOTS = computed(() => DAYS.value.length * PERIODS_PER_DAY.value)

// 学科系→色板槽位，固定顺序（8 色分类色板，经 dataviz 校验器验证）。
// 低频学科（音乐、心美）折入 other，不单独造色——见排课系统前端设计讨论。
const FAMILY_SLOT: Record<string, number | 'other'> = {
  语文: 1,
  数学: 2,
  英语: 3,
  物理: 4,
  综实1: 4,
  化学: 5,
  道法: 6,
  历史: 7,
  体育: 8,
  音乐: 'other',
  美术: 'other',
  心理: 'other',
}

const rows = computed(() =>
  Array.from({ length: N_SLOTS.value }, (_, slot) => ({
    slot,
    day: DAYS.value[Math.floor(slot / PERIODS_PER_DAY.value)],
    period: (slot % PERIODS_PER_DAY.value) + 1,
  })),
)

// 服务端确认过的课表——拖拽只在本地重排这份数据的展示位置，真正落地
// 靠 confirm 时打后端。props.placements 变了（比如切换候选方案、或者
// confirm 成功后父组件重新拉了一次）就整体重置本地状态。
const basePlacements = ref<Placement[]>([])

// 周课时 > 1 的任务在 placements 里有多条记录共用同一个 task_id，只有
// (task_id, 原始 slot) 这一对才能唯一定位到具体某一节课——用它做
// pendingMoves 的 key，而不是单用 task_id（否则拖一节课会把该任务的
// 全部节次一起拖走）。这个 key 只依赖 basePlacements 里各条记录固有的
// task_id/slot，不依赖数组下标，所以哪怕数组因为别的班级 confirm 而被
// 整体替换、下标发生变化，也不会指错对象。
function baseKey(p: Placement): string {
  return `${p.task_id}:${p.slot}`
}

interface DisplayedPlacement extends Placement {
  _key: string
}

interface RevertMessage {
  reason: string
  kinds: string[]
}

// 违规类型很细（校验器有 12 种 kind），按严重程度归成 4 组再着色，比
// 每种 kind 一个颜色更好辨认：结构性冲突（分身/重课/超容）最要紧，禁排
// 类次之，分布类（每日上下限等软性规则）再次，数据类兜底。未收录的新
// kind 落到 other，不需要每新增一种校验器 kind 就来改这里。
const VIOLATION_KIND_GROUP: Record<string, 'structural' | 'forbidden' | 'distribution' | 'data'> = {
  教师分身: 'structural',
  班级重课: 'structural',
  场地超容: 'structural',
  违反禁排: 'forbidden',
  越出窗口: 'forbidden',
  每日下限不足: 'distribution',
  每日上限超出: 'distribution',
  指定星期节数不符: 'distribution',
  缺少连堂: 'distribution',
  单双周未共格: 'distribution',
  教师半天连堂过长: 'distribution',
  课时数不符: 'data',
  规则未被校验: 'data',
}

function kindClass(kind: string): string {
  return `kind-${VIOLATION_KIND_GROUP[kind] ?? 'other'}`
}

const pendingMoves = reactive(new Map<string, number>())   // baseKey -> 目标 slot
const revertMessages = reactive(new Map<number, RevertMessage[]>())
const dirtyClasses = reactive(new Set<number>())
const draggingKey = ref<string | null>(null)
const draggingClassId = ref<number | null>(null)
const draggingFromSlot = ref<number | null>(null)
const confirming = reactive(new Set<number>())

watch(
  () => props.placements,
  (next) => {
    basePlacements.value = next
    pendingMoves.clear()
    revertMessages.clear()
    dirtyClasses.clear()
  },
  { immediate: true },
)

function displayedPlacements(): DisplayedPlacement[] {
  return basePlacements.value.map((p) => {
    const key = baseKey(p)
    const target = pendingMoves.get(key)
    return { ...p, slot: target ?? p.slot, _key: key }
  })
}

function cellPlacements(classId: number, slot: number): DisplayedPlacement[] {
  return displayedPlacements().filter((p) => p.class_id === classId && p.slot === slot)
}

function cellText(classId: number, slot: number): string {
  return cellPlacements(classId, slot)
    .map((p) => (p.parity ? `${p.course}(${p.parity})` : p.course))
    .join('/')
}

function cellFamilyClass(classId: number, slot: number): string {
  const first = cellPlacements(classId, slot)[0]
  if (!first) return ''
  const slotId = FAMILY_SLOT[first.course]
  return slotId ? `family-${slotId}` : 'family-other'
}

function isDraggable(placement: Placement): boolean {
  // 单双周配对课程（parity 非空）这一版先锁定，不支持拖拽——配对语义
  // 比较绕，留到以后需要时再单独设计。
  return placement.parity === null
}

function isCellDraggable(classId: number, slot: number): boolean {
  const here = cellPlacements(classId, slot)
  return here.length === 1 && isDraggable(here[0])
}

function onDragStart(event: DragEvent, placement: DisplayedPlacement) {
  draggingKey.value = placement._key
  draggingClassId.value = placement.class_id
  draggingFromSlot.value = placement.slot
  event.dataTransfer?.setData('text/plain', placement._key)
}

function onDragEnd() {
  draggingKey.value = null
  draggingClassId.value = null
  draggingFromSlot.value = null
}

function onDragOver(event: DragEvent, classId: number, slot: number) {
  // 只允许拖到同一个班级列内、且目标格不是锁定格（单双周配对格）——
  // 不 preventDefault 就等于告诉浏览器这里不是合法落点，drop 事件不会触发。
  if (draggingClassId.value !== classId) return
  const here = cellPlacements(classId, slot)
  if (here.length > 1) return
  if (here.length === 1 && !isDraggable(here[0])) return
  event.preventDefault()
}

function onDrop(event: DragEvent, classId: number, slot: number) {
  event.preventDefault()
  if (draggingKey.value === null || draggingClassId.value !== classId) return

  const target = cellPlacements(classId, slot).filter((p) => p._key !== draggingKey.value)
  if (target.length > 1 || (target.length === 1 && !isDraggable(target[0]))) return

  pendingMoves.set(draggingKey.value, slot)
  if (target.length === 1) {
    pendingMoves.set(target[0]._key, draggingFromSlot.value!)
  }
  dirtyClasses.add(classId)
  draggingKey.value = null
  draggingClassId.value = null
  draggingFromSlot.value = null
}

function isDirty(classId: number): boolean {
  return dirtyClasses.has(classId)
}

function messagesFor(classId: number): RevertMessage[] {
  return revertMessages.get(classId) ?? []
}

function cancel(classId: number) {
  for (const p of basePlacements.value) {
    if (p.class_id === classId) pendingMoves.delete(baseKey(p))
  }
  dirtyClasses.delete(classId)
  revertMessages.delete(classId)
}

async function confirm(classId: number) {
  if (!props.jobId || !props.candidateIndex) return
  const classEntries = basePlacements.value.filter((p) => p.class_id === classId)
  const pendingKeysForClass = classEntries.map(baseKey).filter((key) => pendingMoves.has(key))
  const moves = classEntries
    .filter((p) => pendingMoves.has(baseKey(p)))
    .map((p) => ({ task_id: p.task_id, from_slot: p.slot, to_slot: pendingMoves.get(baseKey(p))! }))
  if (!moves.length) {
    dirtyClasses.delete(classId)
    return
  }

  confirming.add(classId)
  try {
    const result = await adjustCandidate(props.jobId, props.candidateIndex, classId, moves)
    // 服务端返回的是这个班级最终的完整课表——以它为唯一真相整体重绘，
    // 不在本地自己拼状态。
    basePlacements.value = [
      ...basePlacements.value.filter((p) => p.class_id !== classId),
      ...result.placements as Placement[],
    ]
    // 这批 key 是 confirm 前算好的快照——数组已经整体换了一批新对象，
    // 不能再用新 basePlacements 反查该清哪些 key（其他班级的 pendingMoves
    // 完全不受影响，因为 key 本身不依赖数组下标）。
    for (const key of pendingKeysForClass) pendingMoves.delete(key)
    revertMessages.set(classId, result.reverted.map((r) => ({ reason: r.reason, kinds: r.kinds })))
    dirtyClasses.delete(classId)
  } finally {
    confirming.delete(classId)
  }
}
</script>

<template>
  <div class="grid-scroll">
    <table class="schedule-table">
      <thead>
        <tr>
          <th class="col-day">星期</th>
          <th class="col-period">节次</th>
          <th v-for="classId in classes" :key="classId">
            <div class="class-header">
              <span>{{ classId }}班</span>
              <span v-if="isDirty(classId)" class="class-header__actions">
                <button data-test="confirm-button" class="btn btn-primary btn-tiny"
                        :disabled="confirming.has(classId)" @click="confirm(classId)">
                  确认
                </button>
                <button data-test="cancel-button" class="btn btn-secondary btn-tiny"
                        @click="cancel(classId)">
                  取消
                </button>
              </span>
            </div>
            <ul v-if="messagesFor(classId).length" data-test="revert-messages" class="revert-messages">
              <li v-for="(m, i) in messagesFor(classId)" :key="i">
                <span v-for="kind in m.kinds" :key="kind" class="kind-badge" :class="kindClass(kind)"
                      data-test="revert-kind-badge">{{ kind }}</span>
                {{ m.reason }}
              </li>
            </ul>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.slot" data-test="grid-row">
          <td class="col-day">{{ row.day }}</td>
          <td class="col-period">{{ row.period }}</td>
          <td
            v-for="classId in classes"
            :key="classId"
            class="cell"
            :class="[cellFamilyClass(classId, row.slot), { draggable: isCellDraggable(classId, row.slot) }]"
            :draggable="isCellDraggable(classId, row.slot)"
            @dragstart="cellPlacements(classId, row.slot)[0] && onDragStart($event, cellPlacements(classId, row.slot)[0])"
            @dragend="onDragEnd"
            @dragover="onDragOver($event, classId, row.slot)"
            @drop="onDrop($event, classId, row.slot)"
          >
            {{ cellText(classId, row.slot) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.grid-scroll {
  overflow: auto;
  max-height: 70vh;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.schedule-table {
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12.5px;
  min-width: 100%;
}

.schedule-table th,
.schedule-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  border-right: 1px solid var(--border);
  white-space: nowrap;
  text-align: center;
}

.schedule-table thead th {
  position: sticky;
  top: 0;
  z-index: 3;
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
}

.col-day,
.col-period {
  position: sticky;
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  z-index: 1;
}

.col-day {
  left: 0;
  min-width: 56px;
}

.col-period {
  left: 56px;
  min-width: 48px;
}

thead .col-day,
thead .col-period {
  z-index: 4;
}

.cell {
  color: var(--text-primary);
  min-width: 64px;
}

.cell.draggable {
  cursor: grab;
}

.cell.family-1 { background: color-mix(in srgb, var(--family-1) 16%, var(--surface)); }
.cell.family-2 { background: color-mix(in srgb, var(--family-2) 16%, var(--surface)); }
.cell.family-3 { background: color-mix(in srgb, var(--family-3) 16%, var(--surface)); }
.cell.family-4 { background: color-mix(in srgb, var(--family-4) 20%, var(--surface)); }
.cell.family-5 { background: color-mix(in srgb, var(--family-5) 18%, var(--surface)); }
.cell.family-6 { background: color-mix(in srgb, var(--family-6) 14%, var(--surface)); }
.cell.family-7 { background: color-mix(in srgb, var(--family-7) 16%, var(--surface)); }
.cell.family-8 { background: color-mix(in srgb, var(--family-8) 16%, var(--surface)); }
.cell.family-other { background: var(--page-bg); }

tbody tr:hover .cell {
  filter: brightness(0.96);
}

.class-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.class-header__actions {
  display: flex;
  gap: 4px;
}

.btn-tiny {
  padding: 2px 8px;
  font-size: 11px;
}

.revert-messages {
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
  font-size: 10.5px;
  font-weight: 400;
  color: var(--text-critical, #c0392b);
  white-space: normal;
  text-align: left;
}

.kind-badge {
  display: inline-block;
  margin: 0 4px 2px 0;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
}

.kind-badge.kind-structural { background: #c0392b; }
.kind-badge.kind-forbidden { background: #d9822b; }
.kind-badge.kind-distribution { background: #b8960c; }
.kind-badge.kind-data { background: #6b6b6b; }
.kind-badge.kind-other { background: #999; }
</style>
