<script setup lang="ts">
export interface HistoryRow {
  id: string
  label: string
  sublabel: string
}

const props = defineProps<{ title: string; rows: HistoryRow[]; loading: boolean }>()
const emit = defineEmits<{ select: [id: string]; delete: [id: string]; clear: [] }>()
</script>

<template>
  <section class="history-list">
    <header class="history-header">
      <h3>{{ title }}</h3>
      <button v-if="rows.length" data-test="history-clear" class="btn btn-secondary"
              @click="emit('clear')">
        清空
      </button>
    </header>

    <p v-if="loading" class="history-empty">加载中…</p>
    <p v-else-if="!rows.length" class="history-empty">暂无历史记录</p>

    <ul v-else class="history-rows">
      <li v-for="row in rows" :key="row.id" data-test="history-row" class="history-row">
        <button data-test="history-select" class="history-row__main" @click="emit('select', row.id)">
          <span class="history-row__label">{{ row.label }}</span>
          <span class="history-row__sublabel">{{ row.sublabel }}</span>
        </button>
        <button data-test="history-delete" class="btn btn-secondary history-row__delete"
                @click="emit('delete', row.id)">
          删除
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.history-list {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--page-bg);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-header h3 {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
}

.history-empty {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 13px;
}

.history-rows {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-row__main {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  cursor: pointer;
  text-align: left;
}

.history-row__main:hover {
  filter: brightness(0.97);
}

.history-row__label {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

.history-row__sublabel {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
