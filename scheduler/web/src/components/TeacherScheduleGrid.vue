<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Placement {
  class_id: number
  course: string
  teacher: string
  slot: number
  parity: string | null
}

const props = defineProps<{
  placements: Placement[]
  days?: string[]
  periodsPerDay?: number
}>()

const DAYS = computed(() => props.days ?? ['周一', '周二', '周三', '周四', '周五'])
const PERIODS_PER_DAY = computed(() => props.periodsPerDay ?? 9)
const N_SLOTS = computed(() => DAYS.value.length * PERIODS_PER_DAY.value)

const rows = computed(() =>
  Array.from({ length: N_SLOTS.value }, (_, slot) => ({
    slot,
    day: DAYS.value[Math.floor(slot / PERIODS_PER_DAY.value)],
    period: (slot % PERIODS_PER_DAY.value) + 1,
  })),
)

// 教师名单只来自当前候选方案里实际出现过的教师——教务固定占位课程
// （体比/体选等）不生成 placement，其任课教师自然不会出现在这里，
// 不需要额外过滤。
const teachers = computed(() => [...new Set(props.placements.map((p) => p.teacher))].sort())

const selected = ref('')
watch(teachers, (list) => {
  if (!list.includes(selected.value)) selected.value = list[0] ?? ''
}, { immediate: true })

function cellPlacements(slot: number): Placement[] {
  return props.placements.filter((p) => p.teacher === selected.value && p.slot === slot)
}

function cellText(slot: number): string {
  return cellPlacements(slot)
    .map((p) => (p.parity ? `${p.class_id}班${p.course}(${p.parity})` : `${p.class_id}班${p.course}`))
    .join('/')
}
</script>

<template>
  <div class="teacher-grid">
    <div class="teacher-picker">
      <label for="teacher-input">教师</label>
      <input
        id="teacher-input"
        data-test="teacher-input"
        v-model="selected"
        list="teacher-options"
        placeholder="输入或选择教师姓名"
      />
      <datalist id="teacher-options">
        <option v-for="name in teachers" :key="name" :value="name" />
      </datalist>
    </div>

    <p v-if="!teachers.length" class="empty-hint">当前候选方案没有可展示的教师课表。</p>

    <div v-else class="grid-scroll">
      <table class="schedule-table">
        <thead>
          <tr>
            <th class="col-day">星期</th>
            <th class="col-period">节次</th>
            <th>{{ selected || '（未选择）' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.slot" data-test="grid-row">
            <td class="col-day">{{ row.day }}</td>
            <td class="col-period">{{ row.period }}</td>
            <td class="cell">{{ cellText(row.slot) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.teacher-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.teacher-picker {
  display: flex;
  align-items: center;
  gap: 8px;
}

.teacher-picker input {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-primary);
  min-width: 200px;
}

.empty-hint {
  color: var(--text-secondary);
}

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
  min-width: 120px;
}
</style>
