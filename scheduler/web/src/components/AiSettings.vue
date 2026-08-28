<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAiSettings, putAiSettings, testAiSettings } from '../api'

const provider = ref<'openai' | 'anthropic'>('openai')

const openaiConfigured = ref(false)
const openaiBaseUrl = ref('')
const openaiModel = ref('')
const openaiApiKey = ref('')
const openaiMaskedKey = ref<string | null>(null)

const anthropicConfigured = ref(false)
const anthropicSource = ref('none')
const anthropicMaskedKey = ref<string | null>(null)
const anthropicApiKey = ref('')

const error = ref('')
const notice = ref('')
const loading = ref(false)

onMounted(refresh)

async function refresh() {
  error.value = ''
  try {
    const resp = await getAiSettings()
    provider.value = resp.provider === 'anthropic' ? 'anthropic' : 'openai'
    openaiConfigured.value = resp.openai_configured
    openaiBaseUrl.value = resp.openai_base_url ?? ''
    openaiModel.value = resp.openai_model ?? ''
    openaiMaskedKey.value = resp.openai_masked_key
    anthropicConfigured.value = resp.anthropic_configured
    anthropicSource.value = resp.anthropic_source
    anthropicMaskedKey.value = resp.anthropic_masked_key
  } catch (err) {
    error.value = (err as Error).message
  }
}

function anthropicStatusText(): string {
  if (!anthropicConfigured.value) return '未配置'
  if (anthropicSource.value === 'env') return '已配置（来自环境变量）'
  return `已配置（本地，${anthropicMaskedKey.value ?? ''}）`
}

async function save() {
  error.value = ''
  notice.value = ''
  loading.value = true
  try {
    if (provider.value === 'openai') {
      await putAiSettings({
        provider: 'openai',
        openai_base_url: openaiBaseUrl.value.trim() || undefined,
        openai_api_key: openaiApiKey.value.trim() || undefined,
        openai_model: openaiModel.value.trim() || undefined,
      })
    } else {
      await putAiSettings({
        provider: 'anthropic',
        anthropic_api_key: anthropicApiKey.value.trim() || undefined,
      })
    }
    openaiApiKey.value = ''
    anthropicApiKey.value = ''
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
</script>

<template>
  <section class="card ai-settings">
    <h2>AI 设置</h2>
    <p class="hint">
      两种供应商二选一生效：OpenAI 兼容协议（自建/第三方服务，主推）或 Anthropic。
      key 只保存在本机，不会上传到别处；切换供应商不会清空另一边已经填好的信息。
    </p>

    <div class="provider-tabs">
      <button type="button" class="btn" :class="provider === 'openai' ? 'btn-primary' : 'btn-secondary'"
              data-test="provider-openai" @click="provider = 'openai'">
        OpenAI 兼容协议
        <span v-if="openaiConfigured" class="badge badge-good tab-badge">已配置</span>
      </button>
      <button type="button" class="btn" :class="provider === 'anthropic' ? 'btn-primary' : 'btn-secondary'"
              data-test="provider-anthropic" @click="provider = 'anthropic'">
        Anthropic
        <span v-if="anthropicConfigured" class="badge badge-good tab-badge">已配置</span>
      </button>
    </div>

    <div v-if="provider === 'openai'" class="fields" data-test="openai-fields">
      <label class="field">
        Base URL
        <input data-test="openai-base-url-input" v-model="openaiBaseUrl" placeholder="https://your-service.example.com/v1" />
      </label>
      <label class="field">
        模型名
        <input data-test="openai-model-input" v-model="openaiModel" placeholder="gpt-4o-mini" />
      </label>
      <label class="field">
        API key
        <input data-test="openai-key-input" type="password" v-model="openaiApiKey"
              :placeholder="openaiMaskedKey ?? 'sk-…'" />
      </label>
    </div>

    <div v-else class="fields" data-test="anthropic-fields">
      <p class="status-row">
        当前状态：<span data-test="anthropic-status" class="badge"
                       :class="anthropicConfigured ? 'badge-good' : 'badge-neutral'">{{ anthropicStatusText() }}</span>
      </p>
      <label class="field">
        API key
        <input data-test="anthropic-key-input" type="password" v-model="anthropicApiKey" placeholder="sk-ant-…" />
      </label>
    </div>

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
  max-width: 520px;
}

.hint {
  color: var(--text-secondary);
  margin: 8px 0 16px;
  line-height: 1.6;
}

.provider-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.tab-badge {
  margin-left: 6px;
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.status-row {
  margin: 0;
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
