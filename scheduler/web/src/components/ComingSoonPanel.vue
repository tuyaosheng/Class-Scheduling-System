<script setup lang="ts">
defineProps<{ stepEyebrow: string; title: string; body: string }>()
</script>

<template>
  <section class="coming-soon">
    <div class="step-eyebrow">{{ stepEyebrow }}</div>
    <h1 class="page-title">{{ title }}</h1>
    <p class="page-sub">{{ body }}</p>
    <div class="placeholder-card">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5"/>
      </svg>
      <p>这一步还在开发中</p>
    </div>
  </section>
</template>

<style scoped>
.coming-soon { max-width: 760px; }
.step-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--accent); }
.page-title { font-size: 26px; font-weight: 700; letter-spacing: -0.01em; margin-top: 6px; }
.page-sub { font-size: 14px; color: var(--text-secondary); margin-top: 8px; line-height: 1.6; max-width: 560px; }
.placeholder-card {
  margin-top: 28px; border: 1.5px dashed var(--border); border-radius: var(--radius-lg);
  padding: 40px; display: flex; flex-direction: column; align-items: center; gap: 10px;
  color: var(--text-muted); font-size: 13.5px;
}
</style>
