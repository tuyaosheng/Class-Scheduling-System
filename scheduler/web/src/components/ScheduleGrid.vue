<script setup lang="ts">
import { computed } from 'vue'

interface Placement {
  class_id: number
  course: string
  slot: number
  parity: string | null
}

const props = defineProps<{ classes: number[]; placements: Placement[] }>()

const DAYS = ['周一', '周二', '周三', '周四', '周五']
const PERIODS_PER_DAY = 9
const N_SLOTS = DAYS.length * PERIODS_PER_DAY

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
  Array.from({ length: N_SLOTS }, (_, slot) => ({
    slot,
    day: DAYS[Math.floor(slot / PERIODS_PER_DAY)],
    period: (slot % PERIODS_PER_DAY) + 1,
  })),
)

function cellPlacements(classId: number, slot: number): Placement[] {
  return props.placements.filter((p) => p.class_id === classId && p.slot === slot)
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
</script>

<template>
  <div class="grid-scroll">
    <table class="schedule-table">
      <thead>
        <tr>
          <th class="col-day">星期</th>
          <th class="col-period">节次</th>
          <th v-for="classId in classes" :key="classId">{{ classId }}班</th>
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
            :class="cellFamilyClass(classId, row.slot)"
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
</style>
