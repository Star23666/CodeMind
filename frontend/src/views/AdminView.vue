<template>
  <div class="admin-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="page-head">
        <div>
          <el-tag type="warning" effect="plain">管理员</el-tag>
          <h1>系统管理</h1>
          <p>查看运行状态、维护用户和公共资料，并集中处理问答反馈。</p>
        </div>
        <el-button :icon="Refresh" :loading="loadingAll" @click="loadAll">刷新全部</el-button>
      </section>

      <section class="overview-grid">
        <article><span>用户</span><strong>{{ overview.users_active }} / {{ overview.users_total }}</strong><small>启用 / 总数</small></article>
        <article><span>文档</span><strong>{{ overview.documents_total }}</strong><small>{{ overview.documents_failed }} 个失败</small></article>
        <article><span>反馈</span><strong>{{ overview.feedbacks_total }}</strong><small>已提交评价</small></article>
        <article>
          <span>服务就绪</span>
          <strong :class="{ danger: !isReady }">{{ isReady ? "正常" : "异常" }}</strong>
          <small>MySQL {{ checkText("mysql") }} · Chroma {{ checkText("chroma") }}</small>
        </article>
      </section>

      <section class="anomaly-panel">
        <div class="section-head">
          <div><p>运行异常</p><h2>最近失败记录</h2></div>
          <span>只展示业务状态和错误摘要，不展示密钥、Prompt 或私人文档内容。</span>
        </div>
        <el-table :data="overview.recent_anomalies || []" empty-text="暂无失败记录">
          <el-table-column label="类型" width="130">
            <template #default="{ row }">{{ anomalyType(row.resource_type) }}</template>
          </el-table-column>
          <el-table-column prop="resource_id" label="编号" width="120" />
          <el-table-column prop="user_id" label="用户 ID" width="100" />
          <el-table-column prop="message" label="错误摘要" min-width="300" show-overflow-tooltip />
          <el-table-column label="时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </section>

      <section class="management-panel">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="用户管理" name="users">
            <div class="toolbar">
              <el-input v-model="userFilters.query" clearable :prefix-icon="Search" placeholder="用户名或邮箱" @keyup.enter="loadUsers" />
              <el-select v-model="userFilters.role" clearable placeholder="全部角色">
                <el-option label="普通用户" value="user" />
                <el-option label="管理员" value="admin" />
              </el-select>
              <el-select v-model="userFilters.status" clearable placeholder="全部状态">
                <el-option label="启用" value="active" />
                <el-option label="停用" value="disabled" />
              </el-select>
              <el-button :loading="loadingUsers" @click="loadUsers">筛选</el-button>
            </div>
            <el-table v-loading="loadingUsers" :data="users" empty-text="暂无用户">
              <el-table-column prop="id" label="ID" width="80" />
              <el-table-column prop="username" label="用户名" min-width="140" />
              <el-table-column prop="email" label="邮箱" min-width="220" />
              <el-table-column label="角色" width="110">
                <template #default="{ row }"><el-tag :type="row.role === 'admin' ? 'warning' : 'info'" effect="plain">{{ row.role === "admin" ? "管理员" : "用户" }}</el-tag></template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'danger'">{{ row.status === "active" ? "启用" : "停用" }}</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button
                    link
                    :type="row.status === 'active' ? 'danger' : 'primary'"
                    :disabled="row.id === userStore.userId"
                    @click="toggleUserStatus(row)"
                  >{{ row.status === "active" ? "停用" : "启用" }}</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="文档与任务" name="documents">
            <el-alert
              title="私人资料保护"
              description="管理员只能查看私人文档的编号和处理状态；文件名、知识库名称、具体错误、原文和片段不会展示，也不能执行管理操作。"
              type="info"
              show-icon
              :closable="false"
            />
            <div class="toolbar document-toolbar">
              <el-input v-model="documentFilters.query" clearable :prefix-icon="Search" placeholder="上传者；公共文件名" @keyup.enter="loadDocuments" />
              <el-input-number v-model="documentFilters.owner_id" :min="1" controls-position="right" placeholder="用户 ID" />
              <el-input-number v-model="documentFilters.knowledge_base_id" :min="1" controls-position="right" placeholder="知识库 ID" />
              <el-select v-model="documentFilters.parse_status" clearable placeholder="全部状态">
                <el-option v-for="item in parseStatuses" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-select v-model="documentFilters.visibility" clearable placeholder="全部范围">
                <el-option label="公共" value="public" />
                <el-option label="私人（脱敏）" value="private" />
              </el-select>
              <el-button :loading="loadingDocuments" @click="loadDocuments">筛选</el-button>
            </div>
            <el-table v-loading="loadingDocuments" :data="documents" empty-text="暂无文档记录">
              <el-table-column prop="id" label="ID" width="80" />
              <el-table-column label="文档" min-width="210">
                <template #default="{ row }">
                  <div class="table-primary">
                    <strong>{{ row.file_name || `私人文档 #${row.id}` }}</strong>
                    <span>{{ row.knowledge_base_name || `私人知识库 #${row.knowledge_base_id}` }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="上传者" min-width="140">
                <template #default="{ row }">{{ row.uploader_username }} (#{{ row.owner_id }})</template>
              </el-table-column>
              <el-table-column label="范围" width="100">
                <template #default="{ row }"><el-tag effect="plain">{{ row.knowledge_base_visibility === "public" ? "公共" : "私人" }}</el-tag></template>
              </el-table-column>
              <el-table-column label="状态" min-width="160">
                <template #default="{ row }">
                  <div class="table-primary"><el-tag :type="statusType(row.parse_status)">{{ statusText(row.parse_status) }}</el-tag><span v-if="row.error_message" class="error-text">{{ row.error_message }}</span></div>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="190" fixed="right">
                <template #default="{ row }">
                  <template v-if="row.can_manage">
                    <el-button v-if="['pending', 'processing'].includes(row.parse_status)" link type="warning" @click="cancelDocument(row)">取消</el-button>
                    <el-button v-else link type="primary" @click="rebuildDocument(row)">重建</el-button>
                    <el-button link type="danger" @click="removeDocument(row)">删除</el-button>
                  </template>
                  <span v-else class="muted">仅状态可见</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="问答反馈" name="feedbacks">
            <div class="toolbar">
              <el-select v-model="feedbackFilters.rating" clearable placeholder="全部评分">
                <el-option v-for="score in 5" :key="score" :label="`${score} 分`" :value="score" />
              </el-select>
              <el-input-number v-model="feedbackFilters.user_id" :min="1" controls-position="right" placeholder="用户 ID" />
              <el-input-number v-model="feedbackFilters.knowledge_base_id" :min="1" controls-position="right" placeholder="知识库 ID" />
              <el-button :loading="loadingFeedbacks" @click="loadFeedbacks">筛选</el-button>
            </div>
            <el-table v-loading="loadingFeedbacks" :data="feedbacks" empty-text="暂无反馈">
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column label="评分" width="150">
                <template #default="{ row }"><el-rate :model-value="row.rating" disabled /></template>
              </el-table-column>
              <el-table-column label="用户" min-width="130">
                <template #default="{ row }">{{ row.username }} (#{{ row.user_id }})</template>
              </el-table-column>
              <el-table-column label="知识库" min-width="150">
                <template #default="{ row }">{{ row.knowledge_base_name || `私人知识库 #${row.knowledge_base_id}` }}</template>
              </el-table-column>
              <el-table-column label="问题" min-width="260" show-overflow-tooltip>
                <template #default="{ row }">{{ row.content_redacted ? "私人内容已隐藏" : row.question }}</template>
              </el-table-column>
              <el-table-column label="提交时间" width="180">
                <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="90" fixed="right">
                <template #default="{ row }"><el-button link type="primary" @click="selectedFeedback = row">详情</el-button></template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </section>
    </main>

    <el-drawer v-model="feedbackDrawerVisible" title="反馈详情" size="min(620px, 94vw)">
      <div v-if="selectedFeedback" class="feedback-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="用户">{{ selectedFeedback.username }} (#{{ selectedFeedback.user_id }})</el-descriptions-item>
          <el-descriptions-item label="知识库">{{ selectedFeedback.knowledge_base_name || "私人知识库" }} (#{{ selectedFeedback.knowledge_base_id }})</el-descriptions-item>
          <el-descriptions-item label="评分">{{ selectedFeedback.rating }} / 5</el-descriptions-item>
          <el-descriptions-item label="文字反馈">{{ selectedFeedback.comment || "未填写" }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="selectedFeedback.content_redacted"
          title="私人问答内容已隐藏"
          description="管理员可以查看用户主动提交的评分和文字说明，但不能查看私人知识库中的问题、回答或来源。"
          type="info"
          show-icon
          :closable="false"
        />
        <template v-else>
          <section><small>用户问题</small><p>{{ selectedFeedback.question }}</p></section>
          <section><small>AI 回答</small><p>{{ selectedFeedback.answer }}</p></section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Refresh, Search } from "@element-plus/icons-vue";
import {
  getAdminOverview,
  listAdminDocuments,
  listAdminFeedbacks,
  listAdminUsers,
  updateAdminUserStatus,
} from "../api/admin";
import { cancelDocumentProcessing, deleteDocument, reindexDocument } from "../api/documents";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const userStore = useUserStore();
const activeTab = ref("users");
const healthOnline = ref(false);
const loadingAll = ref(false);
const loadingUsers = ref(false);
const loadingDocuments = ref(false);
const loadingFeedbacks = ref(false);
const users = ref([]);
const documents = ref([]);
const feedbacks = ref([]);
const selectedFeedback = ref(null);
const overview = ref({ users_total: 0, users_active: 0, documents_total: 0, documents_failed: 0, feedbacks_total: 0, readiness: {}, recent_anomalies: [] });
const userFilters = reactive({ query: "", role: "", status: "" });
const documentFilters = reactive({ query: "", owner_id: null, knowledge_base_id: null, parse_status: "", visibility: "" });
const feedbackFilters = reactive({ rating: null, user_id: null, knowledge_base_id: null });
const parseStatuses = [
  { value: "pending", label: "等待中" }, { value: "processing", label: "处理中" },
  { value: "completed", label: "已完成" }, { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];
const isReady = computed(() => overview.value.readiness?.status === "ok");
const feedbackDrawerVisible = computed({
  get: () => Boolean(selectedFeedback.value),
  set: (value) => { if (!value) selectedFeedback.value = null; },
});

watch(activeTab, (tab) => {
  if (tab === "users") loadUsers();
  if (tab === "documents") loadDocuments();
  if (tab === "feedbacks") loadFeedbacks();
});

onMounted(loadAll);

async function loadAll() {
  loadingAll.value = true;
  try {
    const [nextOverview] = await Promise.all([getAdminOverview(), loadUsers(), loadDocuments(), loadFeedbacks()]);
    overview.value = nextOverview;
    healthOnline.value = nextOverview.readiness?.status === "ok";
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loadingAll.value = false;
  }
}

function cleanParams(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== "" && item !== null && item !== undefined));
}

async function loadUsers() {
  loadingUsers.value = true;
  try { users.value = await listAdminUsers(cleanParams(userFilters)); }
  catch (error) { ElMessage.error(error.message); }
  finally { loadingUsers.value = false; }
}

async function loadDocuments() {
  loadingDocuments.value = true;
  try { documents.value = await listAdminDocuments(cleanParams(documentFilters)); }
  catch (error) { ElMessage.error(error.message); }
  finally { loadingDocuments.value = false; }
}

async function loadFeedbacks() {
  loadingFeedbacks.value = true;
  try { feedbacks.value = await listAdminFeedbacks(cleanParams(feedbackFilters)); }
  catch (error) { ElMessage.error(error.message); }
  finally { loadingFeedbacks.value = false; }
}

async function toggleUserStatus(user) {
  const nextStatus = user.status === "active" ? "disabled" : "active";
  try {
    await ElMessageBox.confirm(
      nextStatus === "disabled"
        ? `停用“${user.username}”后，其现有登录状态会立即失效。确定继续吗？`
        : `确定重新启用“${user.username}”吗？`,
      nextStatus === "disabled" ? "确认停用用户" : "确认启用用户",
      { confirmButtonText: nextStatus === "disabled" ? "停用" : "启用", cancelButtonText: "取消", type: "warning" },
    );
    const updated = await updateAdminUserStatus(user.id, nextStatus);
    const index = users.value.findIndex((item) => item.id === updated.id);
    if (index >= 0) users.value[index] = updated;
    ElMessage.success(nextStatus === "disabled" ? "用户已停用。" : "用户已启用。 ");
    overview.value = await getAdminOverview();
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error.message || "操作失败。 ");
  }
}

async function cancelDocument(document) {
  try { await cancelDocumentProcessing(document.id); ElMessage.success("处理任务已取消。 "); await refreshDocumentsAndOverview(); }
  catch (error) { ElMessage.error(error.message); }
}

async function rebuildDocument(document) {
  try { await reindexDocument(document.id); ElMessage.success("已提交重建任务。 "); await refreshDocumentsAndOverview(); }
  catch (error) { ElMessage.error(error.message); }
}

async function removeDocument(document) {
  try {
    await ElMessageBox.confirm(`确定删除公共文档“${document.file_name}”吗？此操作无法恢复。`, "确认删除", { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" });
    await deleteDocument(document.id);
    ElMessage.success("公共文档已删除。 ");
    await refreshDocumentsAndOverview();
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error.message || "删除失败。 ");
  }
}

async function refreshDocumentsAndOverview() {
  await loadDocuments();
  overview.value = await getAdminOverview();
}

function checkText(name) { return overview.value.readiness?.checks?.[name] === "ok" ? "正常" : "异常"; }
function anomalyType(value) { return ({ document: "文档", mind_map_job: "知识地图", quiz_session: "AI 出题" })[value] || value; }
function statusText(value) { return ({ pending: "等待中", processing: "处理中", completed: "已完成", failed: "失败", cancelled: "已取消" })[value] || value; }
function statusType(value) { return ({ pending: "info", processing: "warning", completed: "success", failed: "danger", cancelled: "info" })[value] || "info"; }
function formatDate(value) { if (!value) return "时间未知"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
</script>

<style scoped>
.admin-view { min-height: 100vh; padding: 16px 0 56px; }
.page { display: grid; gap: 20px; width: min(1240px, calc(100% - 32px)); margin: 44px auto 0; }
.page-head, .section-head, .toolbar { display: flex; align-items: center; gap: 14px; }
.page-head, .section-head { justify-content: space-between; }
.page-head h1 { margin: 12px 0 8px; color: var(--cm-heading); font-size: 34px; }
.page-head p { margin: 0; color: var(--cm-muted); }
.overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.overview-grid article { display: grid; gap: 6px; padding: 18px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
.overview-grid span, .overview-grid small, .section-head > span, .muted { color: var(--cm-muted); font-size: 13px; }
.overview-grid strong { color: var(--cm-heading); font-size: 26px; }
.overview-grid strong.danger, .error-text { color: var(--cm-danger); }
.anomaly-panel, .management-panel { padding: 22px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
.anomaly-panel { display: grid; gap: 16px; }
.section-head p { margin: 0 0 5px; color: var(--cm-primary); font-size: 13px; font-weight: 800; }
.section-head h2 { margin: 0; color: var(--cm-heading); }
.section-head > span { max-width: 52%; text-align: right; }
.toolbar { flex-wrap: wrap; padding: 10px 0 18px; }
.toolbar .el-input { width: 240px; }
.toolbar .el-select { width: 150px; }
.document-toolbar .el-input-number { width: 150px; }
.management-panel :deep(.el-alert) { margin: 8px 0 10px; }
.table-primary { display: grid; gap: 5px; }
.table-primary strong { color: var(--cm-heading); }
.table-primary span { color: var(--cm-muted); font-size: 12px; }
.feedback-detail { display: grid; gap: 18px; }
.feedback-detail section { padding: 16px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface-soft); }
.feedback-detail small { color: var(--cm-primary); font-weight: 800; }
.feedback-detail p { margin: 10px 0 0; line-height: 1.75; white-space: pre-wrap; }
@media (max-width: 980px) { .overview-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 680px) { .admin-view { padding-top: 8px; } .page { width: min(100% - 20px, 1240px); margin-top: 32px; } .page-head, .section-head { align-items: stretch; flex-direction: column; } .section-head > span { max-width: none; text-align: left; } .overview-grid { grid-template-columns: 1fr; } .toolbar > * { width: 100% !important; } }
</style>
