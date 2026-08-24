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
const pendingMoves = reactive(new Map<number, number>())
const revertMessages = reactive(new Map<number, string[]>())
const dirtyClasses = reactive(new Set<number>())
const draggingTaskId = ref<number | null>(null)
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

function effectiveSlot(p: Placement): number {
  return pendingMoves.get(p.task_id) ?? p.slot
}

function displayedPlacements(): Placement[] {
  return basePlacements.value.map((p) =>
    pendingMoves.has(p.task_id) ? { ...p, slot: pendingMoves.get(p.task_id)! } : p,
  )
}

function cellPlacements(classId: number, slot: number): Placement[] {
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

function onDragStart(event: DragEvent, taskId: number) {
  draggingTaskId.value = taskId
  event.dataTransfer?.setData('text/plain', String(taskId))
}

function onDragEnd() {
  draggingTaskId.value = null
}

function draggedTaskClassId(): number | null {
  if (draggingTaskId.value === null) return null
  const task = basePlacements.value.find((p) => p.task_id === draggingTaskId.value)
  return task ? task.class_id : null
}

function onDragOver(event: DragEvent, classId: number, slot: number) {
  // 只允许拖到同一个班级列内、且目标格不是锁定格（单双周配对格）——
  // 不 preventDefault 就等于告诉浏览器这里不是合法落点，drop 事件不会触发。
  if (draggedTaskClassId() !== classId) return
  const here = cellPlacements(classId, slot)
  if (here.length > 1) return
  if (here.length === 1 && !isDraggable(here[0])) return
  event.preventDefault()
}

function onDrop(event: DragEvent, classId: number, slot: number) {
  event.preventDefault()
  const taskId = draggingTaskId.value
  if (taskId === null) return
  const dragged = displayedPlacements().find((p) => p.task_id === taskId)
  if (!dragged || dragged.class_id !== classId) return

  const target = cellPlacements(classId, slot).filter((p) => p.task_id !== taskId)
  if (target.length > 1 || (target.length === 1 && !isDraggable(target[0]))) return

  const fromSlot = dragged.slot
  pendingMoves.set(taskId, slot)
  if (target.length === 1) {
    pendingMoves.set(target[0].task_id, fromSlot)
  }
  dirtyClasses.add(classId)
  draggingTaskId.value = null
}

function isDirty(classId: number): boolean {
  return dirtyClasses.has(classId)
}

function messagesFor(classId: number): string[] {
  return revertMessages.get(classId) ?? []
}

function cancel(classId: number) {
  for (const p of basePlacements.value) {
    if (p.class_id === classId) pendingMoves.delete(p.task_id)
  }
  dirtyClasses.delete(classId)
  revertMessages.delete(classId)
}

async function confirm(classId: number) {
  if (!props.jobId || !props.candidateIndex) return
  const moves = basePlacements.value
    .filter((p) => p.class_id === classId && pendingMoves.has(p.task_id))
    .map((p) => ({ task_id: p.task_id, to_slot: pendingMoves.get(p.task_id)! }))
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
    for (const p of basePlacements.value) {
      if (p.class_id === classId) pendingMoves.delete(p.task_id)
    }
    revertMessages.set(classId, result.reverted.map((r) => r.reason))
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
              <li v-for="(m, i) in messagesFor(classId)" :key="i">{{ m }}</li>
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
            @dragstart="cellPlacements(classId, row.slot)[0] && onDragStart($event, cellPlacements(classId, row.slot)[0].task_id)"
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
</style>
