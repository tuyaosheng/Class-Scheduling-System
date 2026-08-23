<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getAiSettings, putAiSettings, testAiSettings } from '../api'

const configured = ref(false)
const sourceText = ref('')
const apiKey = ref('')
const error = ref('')
const notice = ref('')
const loading = ref(false)

onMounted(refresh)

async function refresh() {
  error.value = ''
  try {
    const resp = await getAiSettings()
    configured.value = resp.configured
    if (!resp.configured) {
      sourceText.value = '未配置'
    } else if (resp.source === 'local') {
      sourceText.value = `已配置（本地，${resp.masked_key ?? ''}）`
    } else {
      sourceText.value = '已配置（来自环境变量）'
    }
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function save() {
  error.value = ''
  notice.value = ''
  if (!apiKey.value.trim()) {
    error.value = '请先填写 API key'
    return
  }
  loading.value = true
  try {
    await putAiSettings(apiKey.value.trim())
    apiKey.value = ''
    notice.value = '已保存'
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

async function testConnection() {
  error.value = ''
  notice.value = ''
  loading.value = true
  try {
    await testAiSettings()
    notice.value = '连接成功'
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

const statusBadgeClass = computed(() => (configured.value ? 'badge-good' : 'badge-neutral'))
</script>

<template>
  <section class="card ai-settings">
    <h2>AI 设置</h2>
    <p class="hint">
      AI 规则解析用 Anthropic API。key 只保存在本机，不会上传到别处。
    </p>
    <p class="status-row">
      当前状态：<span data-test="ai-status" class="badge" :class="statusBadgeClass">{{ sourceText }}</span>
    </p>

    <label class="field key-field">
      API key
      <input data-test="ai-key-input" type="password" v-model="apiKey" placeholder="sk-…" />
    </label>

    <div class="actions">
      <button data-test="ai-save-button" class="btn btn-primary" :disabled="loading" @click="save">保存</button>
      <button data-test="ai-test-button" class="btn btn-secondary" :disabled="loading" @click="testConnection">
        测试连接
      </button>
    </div>

    <p v-if="error" data-test="error" class="alert alert-critical">{{ error }}</p>
    <p v-if="notice" data-test="notice" class="badge badge-good notice">{{ notice }}</p>
  </section>
</template>

<style scoped>
.ai-settings {
  max-width: 480px;
}

.hint {
  color: var(--text-secondary);
  margin: 8px 0 12px;
}

.status-row {
  margin: 0 0 20px;
}

.key-field {
  margin-bottom: 16px;
}

.actions {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.notice {
  width: fit-content;
}
</style>
