<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getCourses, getVenues, type VenueItem } from '../api'

interface Placement {
  class_id: number
  course: string
  slot: number
}

const props = defineProps<{
  placements: Placement[]
  grade: string
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

const venues = ref<VenueItem[]>([])
const courseVenue = ref<Record<string, string>>({})
const error = ref('')

async function refresh() {
  error.value = ''
  try {
    const [coursesResp, venuesResp] = await Promise.all([getCourses(props.grade), getVenues()])
    const map: Record<string, string> = {}
    for (const c of coursesResp.courses) {
      if (c.venue) map[c.name] = c.venue
    }
    courseVenue.value = map
    venues.value = venuesResp.venues
  } catch (err) {
    error.value = (err as Error).message
  }
}

onMounted(refresh)

function countAt(venueName: string, slot: number): number {
  return props.placements.filter(
    (p) => p.slot === slot && courseVenue.value[p.course] === venueName,
  ).length
}

function isOverCapacity(venue: VenueItem, slot: number): boolean {
  return venue.capacity !== null && countAt(venue.name, slot) > venue.capacity
}

function cellText(venue: VenueItem, slot: number): string {
  const count = countAt(venue.name, slot)
  if (!count) return ''
  return venue.capacity !== null ? `${count}/${venue.capacity}` : `${count}`
}
</script>

<template>
  <div class="venue-grid">
    <p v-if="error" class="alert alert-critical">{{ error }}</p>

    <p v-else-if="!venues.length" class="empty-hint">尚未配置任何场地。</p>

    <div v-else class="grid-scroll">
      <table class="schedule-table">
        <thead>
          <tr>
            <th class="col-day">星期</th>
            <th class="col-period">节次</th>
            <th v-for="venue in venues" :key="venue.name">
              {{ venue.name }}<span v-if="venue.capacity !== null" class="capacity">（容量 {{ venue.capacity }}）</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.slot" data-test="grid-row">
            <td class="col-day">{{ row.day }}</td>
            <td class="col-period">{{ row.period }}</td>
            <td
              v-for="venue in venues"
              :key="venue.name"
              class="cell"
              :class="{ 'cell-over': isOverCapacity(venue, row.slot) }"
            >
              {{ cellText(venue, row.slot) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.venue-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.capacity {
  font-weight: 400;
  color: var(--text-secondary);
  font-size: 11px;
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
  min-width: 90px;
}

.cell-over {
  background: color-mix(in srgb, var(--text-critical, #c0392b) 20%, var(--surface));
  font-weight: 600;
}
</style>
