<script setup lang="ts">
import { computed } from 'vue'

interface Candidate {
  index: number
  objective: number | null
  stats: string
}

const props = defineProps<{ candidates: Candidate[]; activeIndex: number }>()

// 现在的实现（见 CLAUDE.md M4 现状）是一次求解 + solve_many 生成 N 个彼此
// 有差异度的候选解，不是原设计文档 §7.1 的"同一个解经 SolutionCallback
// 逐帧变好"。objective 曲线因此画的是"候选 1..N 各自的软约束加权目标值"，
// 不是"同一个解在时间轴上下降"——数值越低越好，柱子之间没有先后优化关系。
const withObjective = computed(() => props.candidates.filter((c) => c.objective !== null))
const maxObjective = computed(() => Math.max(1, ...withObjective.value.map((c) => c.objective as number)))

const activeCandidate = computed(() => props.candidates.find((c) => c.index === props.activeIndex))

function barHeight(objective: number): number {
  return Math.max(4, Math.round((objective / maxObjective.value) * 100))
}
</script>

<template>
  <div class="solve-monitor">
    <div v-if="!withObjective.length" class="empty-hint">
      本批候选方案没有软约束目标值可展示（当前生效的规则都是硬约束，或还没有候选方案）。
    </div>

    <div v-else class="objective-chart">
      <p class="chart-caption">软约束加权目标值（越低越好，候选之间没有先后优化关系，只是各自独立求解的结果）</p>
      <div class="bars">
        <div v-for="c in withObjective" :key="c.index" class="bar-col">
          <div class="bar" :style="{ height: barHeight(c.objective as number) + '%' }"
               :class="{ active: c.index === activeIndex }" />
          <span class="bar-label">方案{{ c.index }}</span>
          <span class="bar-value">{{ c.objective }}</span>
        </div>
      </div>
    </div>

    <div v-if="activeCandidate" class="solver-stats">
      <p class="chart-caption">当前方案的求解器日志（CP-SAT ResponseStats 原文）</p>
      <pre v-if="activeCandidate.stats" data-test="solver-stats-text">{{ activeCandidate.stats }}</pre>
      <p v-else class="empty-hint">没有可展示的求解器日志。</p>
    </div>
  </div>
</template>

<style scoped>
.solve-monitor {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.empty-hint {
  color: var(--text-secondary);
  font-size: 13px;
}

.chart-caption {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 0 10px;
}

.bars {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  height: 160px;
  padding: 0 4px;
}

.bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  height: 100%;
  min-width: 48px;
}

.bar {
  width: 28px;
  background: var(--accent-wash);
  border: 1px solid var(--accent);
  border-radius: 4px 4px 0 0;
}

.bar.active {
  background: var(--accent);
}

.bar-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.bar-value {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  font-weight: 600;
}

.solver-stats pre {
  background: var(--surface-raised);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  font-size: 12px;
  white-space: pre-wrap;
  margin: 0;
}
</style>
