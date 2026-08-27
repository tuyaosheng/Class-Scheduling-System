<script setup lang="ts">
interface Item {
  kind: string
  detail: string
}

defineProps<{
  title: string
  items: Item[]
  tone?: 'warning' | 'critical'
}>()
</script>

<template>
  <div v-if="items.length" class="issue-list" :class="`issue-list--${tone ?? 'warning'}`">
    <h3>{{ title }}（{{ items.length }}）</h3>
    <ul>
      <li v-for="(item, i) in items" :key="i" data-test="issue-item">
        <span class="issue-kind">{{ item.kind }}</span>
        <span class="issue-detail">{{ item.detail }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.issue-list {
  border-radius: var(--radius-md);
  padding: 10px 14px;
  font-size: 13px;
}

.issue-list--warning {
  background: var(--status-warning-wash);
}

.issue-list--critical {
  background: var(--status-critical-wash);
}

.issue-list h3 {
  font-size: 12.5px;
  font-weight: 700;
  margin: 0 0 6px;
}

.issue-list--warning h3 {
  color: #6b4700;
}

.issue-list--critical h3 {
  color: #8a2323;
}

.issue-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.issue-list li {
  display: flex;
  gap: 8px;
  line-height: 1.5;
}

.issue-kind {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--text-primary);
}

.issue-detail {
  color: var(--text-secondary);
}
</style>
