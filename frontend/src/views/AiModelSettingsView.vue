<template>
  <div class="model-settings-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="page-head">
        <div>
          <el-button text class="back-button" @click="router.push({ name: 'me' })">← 返回我的</el-button>
          <h1>AI 模型设置</h1>
          <p class="intro">管理并切换回答时使用的模型。</p>
        </div>
      </section>

      <el-skeleton v-if="loading" :rows="6" animated />

      <template v-else-if="overview">
        <section class="section-block">
          <div class="section-head">
            <div>
              <h2>模型配置</h2>
              <span>个人预设 {{ overview.configs.length }} / {{ overview.max_presets }}</span>
            </div>
            <el-button
              type="primary"
              :disabled="overview.configs.length >= overview.max_presets"
              @click="openCreateDialog"
            >
              新增配置
            </el-button>
          </div>

          <div class="config-grid">
            <article
              class="config-card system-config-card"
              :class="{ active: overview.effective_source === 'system' }"
            >
              <div class="card-top">
                <div class="model-logo system-logo">SYS</div>
                <div class="model-main">
                  <div class="model-title-row">
                    <strong>系统默认模型</strong>
                    <el-tag
                      v-if="overview.effective_source === 'system'"
                      type="success"
                      effect="dark"
                      size="small"
                    >
                      当前启用
                    </el-tag>
                  </div>
                  <span>服务端配置</span>
                </div>
              </div>

              <dl class="config-details">
                <div>
                  <dt>模型名称</dt>
                  <dd>{{ overview.system_default.model }}</dd>
                </div>
              </dl>

              <div class="test-state">
                <el-tag :type="overview.system_default.configured ? 'success' : 'warning'" effect="plain" size="small">
                  {{ overview.system_default.configured ? "可用" : "未配置" }}
                </el-tag>
              </div>

              <div class="card-actions">
                <el-button
                  type="primary"
                  :disabled="overview.effective_source === 'system'"
                  :loading="switchingSystem"
                  @click="selectSystemDefault"
                >
                  {{ overview.effective_source === "system" ? "正在使用" : "设为当前模型" }}
                </el-button>
              </div>
            </article>

            <article
              v-for="config in overview.configs"
              :key="config.id"
              class="config-card"
              :class="{ active: config.is_active }"
            >
              <div class="card-top">
                <div class="model-logo">{{ config.name.slice(0, 2).toUpperCase() }}</div>
                <div class="model-main">
                  <div class="model-title-row">
                    <strong>{{ config.name }}</strong>
                    <el-tag v-if="config.is_active" type="success" effect="dark" size="small">当前启用</el-tag>
                  </div>
                  <span>{{ providerLabel(config.provider) }}</span>
                </div>
                <el-dropdown trigger="click">
                  <el-button text aria-label="配置操作">•••</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="openEditDialog(config)">编辑</el-dropdown-item>
                      <el-dropdown-item divided @click="removeConfig(config)">
                        <span class="danger-text">删除</span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>

              <dl class="config-details">
                <div>
                  <dt>模型名称</dt>
                  <dd>{{ config.model }}</dd>
                </div>
                <div>
                  <dt>API 地址</dt>
                  <dd :title="config.base_url">{{ config.base_url }}</dd>
                </div>
                <div>
                  <dt>API Key</dt>
                  <dd>{{ config.masked_api_key }}</dd>
                </div>
              </dl>

              <div class="test-state">
                <el-tag :type="statusMeta(config.test_status).type" effect="plain" size="small">
                  {{ statusMeta(config.test_status).label }}
                </el-tag>
                <span v-if="config.test_status === 'failed' && config.test_message">{{ config.test_message }}</span>
              </div>

              <div class="card-actions">
                <el-button
                  :loading="testingId === config.id"
                  :disabled="testingId !== null || cooldownRemaining > 0"
                  @click="runConnectionTest(config)"
                >
                  {{ testingId === config.id ? "测试中" : cooldownRemaining > 0 ? `${cooldownRemaining}s 后可测试` : "测试连接" }}
                </el-button>
                <el-button
                  type="primary"
                  :disabled="config.test_status !== 'success' || config.is_active"
                  :loading="activatingId === config.id"
                  @click="activateConfig(config)"
                >
                  {{ config.is_active ? "正在使用" : "设为当前模型" }}
                </el-button>
              </div>
            </article>
          </div>
        </section>
      </template>
    </main>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑模型配置' : '新增模型配置'"
      width="min(600px, 94vw)"
      destroy-on-close
    >
      <el-form label-position="top" @submit.prevent>
        <div class="form-row">
          <el-form-item label="配置名称" required>
            <el-input v-model="form.name" maxlength="80" placeholder="例如：硅基流动 - DeepSeek" />
          </el-form-item>
          <el-form-item label="服务类型" required>
            <el-select v-model="form.provider" style="width: 100%" @change="applyProviderSuggestion">
              <el-option label="硅基流动" value="siliconflow" />
              <el-option label="OpenAI" value="openai" />
              <el-option label="其他兼容服务（需管理员放行）" value="openai_compatible" />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item label="API Base URL" required>
          <el-input v-model="form.base_url" placeholder="https://api.example.com/v1" />
        </el-form-item>

        <el-form-item label="模型名称" required>
          <el-input v-model="form.model" placeholder="例如：deepseek-ai/DeepSeek-V4-Flash" />
        </el-form-item>

        <el-form-item :label="editingId ? 'API Key（留空表示不修改）' : 'API Key'" :required="!editingId">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="editingId ? '已加密保存；如需更换请重新输入' : '请输入 API Key'"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import {
  activateLlmConfig,
  createLlmConfig,
  deleteLlmConfig,
  getLlmConfigOverview,
  testLlmConfig,
  updateLlmConfig,
  useSystemDefaultLlm,
} from "../api/llmConfigs";
import AppHeader from "../components/layout/AppHeader.vue";

const router = useRouter();
const healthOnline = ref(false);
const loading = ref(true);
const overview = ref(null);
const dialogVisible = ref(false);
const editingId = ref(null);
const saving = ref(false);
const testingId = ref(null);
const activatingId = ref(null);
const switchingSystem = ref(false);
const cooldownUntil = ref(0);
const clock = ref(Date.now());
let clockTimer = null;

const form = reactive({
  name: "",
  provider: "openai_compatible",
  base_url: "",
  model: "",
  api_key: "",
});

const cooldownRemaining = computed(() =>
  Math.max(0, Math.ceil((cooldownUntil.value - clock.value) / 1000)),
);

onMounted(async () => {
  clockTimer = window.setInterval(() => {
    clock.value = Date.now();
  }, 1000);
  await Promise.all([checkHealth(), loadOverview()]);
});

onBeforeUnmount(() => {
  if (clockTimer) window.clearInterval(clockTimer);
});

async function checkHealth() {
  try {
    healthOnline.value = (await getHealth()).status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadOverview() {
  try {
    overview.value = await getLlmConfigOverview();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  Object.assign(form, {
    name: "",
    provider: "openai_compatible",
    base_url: "",
    model: "",
    api_key: "",
  });
}

function openCreateDialog() {
  editingId.value = null;
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(config) {
  editingId.value = config.id;
  Object.assign(form, {
    name: config.name,
    provider: config.provider,
    base_url: config.base_url,
    model: config.model,
    api_key: "",
  });
  dialogVisible.value = true;
}

function applyProviderSuggestion(provider) {
  if (form.base_url.trim()) return;
  if (provider === "siliconflow") form.base_url = "https://api.siliconflow.cn/v1";
  if (provider === "openai") form.base_url = "https://api.openai.com/v1";
}

async function saveConfig() {
  const payload = {
    name: form.name.trim(),
    provider: form.provider,
    base_url: form.base_url.trim(),
    model: form.model.trim(),
  };
  if (!payload.name || !payload.base_url || !payload.model) {
    ElMessage.warning("请完整填写配置名称、API 地址和模型名称。");
    return;
  }
  if (!editingId.value && !form.api_key.trim()) {
    ElMessage.warning("请输入 API Key。");
    return;
  }
  if (form.api_key.trim()) payload.api_key = form.api_key.trim();

  saving.value = true;
  try {
    if (editingId.value) {
      await updateLlmConfig(editingId.value, payload);
      ElMessage.success("配置已更新，请重新测试连接后启用。");
    } else {
      await createLlmConfig(payload);
      ElMessage.success("配置已保存，请先测试连接。");
    }
    dialogVisible.value = false;
    await loadOverview();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function runConnectionTest(config) {
  testingId.value = config.id;
  try {
    const result = await testLlmConfig(config.id);
    ElMessage.success(`${result.message}，耗时 ${result.latency_ms} ms。`);
  } catch (error) {
    if (error.status === 429 && error.retryAfter) {
      cooldownUntil.value = Date.now() + error.retryAfter * 1000;
    }
    ElMessage.error(error.message);
  } finally {
    if (overview.value) {
      cooldownUntil.value = Math.max(
        cooldownUntil.value,
        Date.now() + overview.value.test_cooldown_seconds * 1000,
      );
    }
    testingId.value = null;
    await loadOverview();
  }
}

async function activateConfig(config) {
  activatingId.value = config.id;
  try {
    overview.value = await activateLlmConfig(config.id);
    ElMessage.success(`已切换到“${config.name}”。`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    activatingId.value = null;
  }
}

async function selectSystemDefault() {
  switchingSystem.value = true;
  try {
    overview.value = await useSystemDefaultLlm();
    ElMessage.success("已切换到系统默认模型。");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    switchingSystem.value = false;
  }
}

async function removeConfig(config) {
  try {
    await ElMessageBox.confirm(
      `确定删除模型配置“${config.name}”吗？已保存的 API Key 也会一并删除。`,
      "确认删除模型配置",
      {
        confirmButtonText: "确定删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    await deleteLlmConfig(config.id);
    ElMessage.success(config.is_active ? "配置已删除，已自动恢复系统默认模型。" : "配置已删除。");
    await loadOverview();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.message || "删除配置失败。");
    }
  }
}

function providerLabel(provider) {
  return {
    siliconflow: "硅基流动",
    openai: "OpenAI",
    openai_compatible: "OpenAI 兼容服务",
  }[provider] || provider;
}

function statusMeta(status) {
  return {
    success: { label: "测试成功", type: "success" },
    failed: { label: "测试失败", type: "danger" },
    untested: { label: "尚未测试", type: "info" },
  }[status] || { label: status, type: "info" };
}
</script>

<style scoped>
.model-settings-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.page {
  width: min(1180px, calc(100% - 32px));
  margin: 44px auto 0;
}

.page-head,
.section-head,
.card-top,
.model-title-row,
.card-actions {
  display: flex;
  align-items: center;
}

.page-head {
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.back-button {
  margin: 0 0 10px -14px;
}

.page-head h1 {
  margin: 0 0 10px;
  color: var(--cm-heading);
  font-size: clamp(30px, 5vw, 46px);
}

.intro,
.section-head span,
.model-main > span,
.test-state span {
  color: var(--cm-muted);
}

.intro {
  max-width: 720px;
  margin: 0;
  line-height: 1.7;
}

.section-block {
  margin-bottom: 22px;
  padding: 24px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.section-head {
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.section-head h2 {
  margin: 0 0 5px;
  color: var(--cm-heading);
  font-size: 25px;
}

.config-card {
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface-soft);
}

.model-logo {
  display: grid;
  width: 50px;
  height: 50px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 15px;
  color: #ffffff;
  background: linear-gradient(135deg, var(--cm-primary), #38bdf8);
  font-size: 13px;
  font-weight: 900;
}

.system-logo {
  background: linear-gradient(135deg, #475569, #0f172a);
}

.model-main {
  min-width: 0;
  flex: 1;
}

.model-title-row {
  flex-wrap: wrap;
  gap: 9px;
}

.model-title-row strong {
  overflow-wrap: anywhere;
  color: var(--cm-heading);
  font-size: 18px;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.config-card {
  display: grid;
  gap: 18px;
  padding: 18px;
}

.config-card.active {
  border-color: var(--cm-primary);
  box-shadow: 0 0 0 2px var(--cm-primary-soft);
}

.card-top {
  gap: 13px;
}

.danger-text {
  color: var(--el-color-danger);
}

.config-details {
  display: grid;
  gap: 10px;
  margin: 0;
}

.config-details div {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
}

.config-details dt {
  color: var(--cm-muted);
  font-size: 13px;
}

.config-details dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--cm-heading);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.test-state {
  display: flex;
  min-height: 25px;
  align-items: center;
  gap: 8px;
}

.test-state span {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-actions {
  justify-content: flex-end;
  gap: 8px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 820px) {
  .page-head {
    align-items: stretch;
    flex-direction: column;
  }

  .config-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .model-settings-view {
    padding-top: 8px;
  }

  .page {
    width: min(100% - 20px, 1180px);
    margin-top: 32px;
  }

  .section-block {
    padding: 18px;
  }

  .section-head,
  .form-row {
    display: grid;
    grid-template-columns: 1fr;
  }

  .card-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
