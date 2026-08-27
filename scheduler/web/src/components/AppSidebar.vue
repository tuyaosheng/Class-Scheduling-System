<script setup lang="ts">
import { computed } from 'vue'

export interface StepDef {
  id: number
  label: string
  meta?: string
}

const props = defineProps<{
  steps: StepDef[]
  currentStep: number
  doneSteps: number[]
  grades: string[]
  activeGrade: string
  showingSettings: boolean
}>()

const emit = defineEmits<{
  'select-step': [id: number]
  'select-grade': [name: string]
  'add-grade': []
  'open-settings': []
}>()

const progressPct = computed(() => {
  if (!props.steps.length) return 0
  return Math.round((props.doneSteps.length / props.steps.length) * 100)
})

function stateOf(id: number): 'done' | 'current' | 'upcoming' {
  if (id === props.currentStep) return 'current'
  if (props.doneSteps.includes(id)) return 'done'
  return 'upcoming'
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-title">排课系统</div>
      <div class="brand-sub">初中排课工作台</div>
    </div>

    <div class="grade-switcher">
      <button
        v-for="g in grades"
        :key="g"
        data-test="grade-pill"
        class="grade-pill"
        :class="{ active: g === activeGrade }"
        @click="emit('select-grade', g)"
      >{{ g }}</button>
      <button data-test="add-grade-pill" class="grade-pill add" @click="emit('add-grade')">
        <svg class="icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        添加年级
      </button>
    </div>

    <div class="nav-progress">
      <div class="nav-progress-track"><div class="nav-progress-fill" :style="{ width: progressPct + '%' }"></div></div>
      <div class="nav-progress-label">{{ doneSteps.length }} / {{ steps.length }}</div>
    </div>

    <nav class="nav-list">
      <button
        v-for="step in steps"
        :key="step.id"
        data-test="nav-step"
        class="nav-item"
        :class="stateOf(step.id)"
        @click="emit('select-step', step.id)"
      >
        <span class="step-badge">
          <svg v-if="stateOf(step.id) === 'done'" class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
          <template v-else>{{ step.id }}</template>
        </span>
        <span class="step-label">{{ step.label }}</span>
        <span v-if="step.meta" class="step-meta">{{ step.meta }}</span>
      </button>
    </nav>

    <div class="sidebar-foot">
      <button data-test="open-settings" class="sidebar-foot-link" :class="{ active: showingSettings }" @click="emit('open-settings')">
        <svg class="icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
        系统设置 · AI 接入
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 268px;
  flex-shrink: 0;
  background: var(--surface-raised);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 28px 18px;
  gap: 22px;
  overflow-y: auto;
  height: 100vh;
  position: sticky;
  top: 0;
}

.brand { display: flex; flex-direction: column; gap: 2px; padding: 0 6px; }
.brand-title { font-size: 16px; font-weight: 700; letter-spacing: -0.01em; color: var(--text-primary); }
.brand-sub { font-size: 12px; color: var(--text-muted); }

.grade-switcher { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 6px; }
.grade-pill {
  padding: 6px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 600;
  border: 1px solid var(--border); color: var(--text-secondary); background: var(--surface);
  cursor: pointer;
}
.grade-pill.active { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.grade-pill.add { border-style: dashed; color: var(--text-muted); display: inline-flex; align-items: center; gap: 4px; }

.nav-progress { padding: 0 6px; display: flex; align-items: center; gap: 8px; }
.nav-progress-track { flex: 1; height: 4px; border-radius: 999px; background: var(--border); overflow: hidden; }
.nav-progress-fill { height: 100%; background: var(--accent); border-radius: 999px; }
.nav-progress-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; font-variant-numeric: tabular-nums; }

.nav-list { display: flex; flex-direction: column; gap: 3px; }
.nav-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: var(--radius-md);
  border: none; background: transparent; cursor: pointer; text-align: left; width: 100%;
}
.nav-item .step-badge {
  width: 24px; height: 24px; border-radius: 999px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700;
}
.nav-item .step-label { font-size: 13.5px; font-weight: 600; flex: 1; }
.nav-item .step-meta { font-size: 11px; color: var(--text-muted); }

.nav-item.done .step-badge { background: var(--status-good-wash); color: var(--status-good); }
.nav-item.done .step-label { color: var(--text-secondary); }
.nav-item.current { background: var(--accent-wash); }
.nav-item.current .step-badge { background: var(--accent); color: var(--accent-ink); }
.nav-item.current .step-label { color: var(--accent); }
.nav-item.upcoming .step-badge { background: var(--page-bg); color: var(--text-muted); border: 1px solid var(--border); }
.nav-item.upcoming .step-label { color: var(--text-muted); }

.sidebar-foot { margin-top: auto; padding: 12px 6px 0; border-top: 1px solid var(--border); }
.sidebar-foot-link {
  display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-secondary);
  padding: 8px 6px; border: none; background: transparent; width: 100%; text-align: left; cursor: pointer; border-radius: var(--radius-sm);
}
.sidebar-foot-link.active { color: var(--accent); background: var(--accent-wash); }

.icon { display: block; }
</style>
