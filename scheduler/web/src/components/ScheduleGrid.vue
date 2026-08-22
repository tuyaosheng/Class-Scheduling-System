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

const rows = computed(() =>
  Array.from({ length: N_SLOTS }, (_, slot) => ({
    slot,
    day: DAYS[Math.floor(slot / PERIODS_PER_DAY)],
    period: (slot % PERIODS_PER_DAY) + 1,
  })),
)

function cellText(classId: number, slot: number): string {
  return props.placements
    .filter((p) => p.class_id === classId && p.slot === slot)
    .map((p) => (p.parity ? `${p.course}(${p.parity})` : p.course))
    .join('/')
}
</script>

<template>
  <table>
    <thead>
      <tr>
        <th>星期</th>
        <th>节次</th>
        <th v-for="classId in classes" :key="classId">{{ classId }}班</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.slot" data-test="grid-row">
        <td>{{ row.day }}</td>
        <td>{{ row.period }}</td>
        <td v-for="classId in classes" :key="classId">{{ cellText(classId, row.slot) }}</td>
      </tr>
    </tbody>
  </table>
</template>
