<template>
  <div class="me-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="page-head">
        <div>
          <el-tag effect="plain">个人中心</el-tag>
          <h1>我的知识库</h1>
          <p>创建和维护你的私人知识库，也可以随时修改名称与描述。</p>
        </div>
        <el-button type="primary" plain @click="goDocuments">去文档上传</el-button>
      </section>

      <section class="profile-grid">
        <article class="panel profile-panel">
          <div class="avatar">{{ initials }}</div>
          <div>
            <p>当前用户</p>
            <h2>{{ userStore.displayName }}</h2>
            <span>{{ userStore.user?.email || "暂未填写邮箱" }}</span>
          </div>
        </article>

        <article class="panel stat-panel">
          <div>
            <span>知识库</span>
            <strong>{{ knowledgeBases.length }}</strong>
          </div>
          <div>
            <span>文档</span>
            <strong>{{ documents.length }}</strong>
          </div>
        </article>
      </section>

      <button class="model-settings-entry" type="button" @click="goModelSettings">
        <span class="entry-icon">AI</span>
        <span class="entry-copy">
          <small>AI 模型设置</small>
          <strong>管理和切换你的大模型 API</strong>
          <span>管理系统默认与个人模型配置。</span>
        </span>
        <span class="entry-action">进入设置 →</span>
      </button>

      <section class="manager-grid">
        <article class="panel create-panel">
          <div class="panel-head">
            <div>
              <p>新建知识库</p>
              <h2>为不同资料分组</h2>
            </div>
          </div>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="名称">
              <el-input v-model="kbForm.name" placeholder="例如：课程资料、项目文档" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="kbForm.description" type="textarea" :rows="3" placeholder="简单说明用途" />
            </el-form-item>
            <el-button type="primary" :loading="creating" @click="createKb">创建</el-button>
          </el-form>
        </article>

        <article class="panel list-panel">
          <div class="panel-head">
            <div>
              <p>已有知识库</p>
              <h2>只展示当前用户的数据</h2>
            </div>
            <el-button text @click="loadData">刷新</el-button>
          </div>

          <div class="kb-list">
            <div v-for="base in knowledgeBases" :key="base.id" class="kb-item">
              <div>
                <strong>{{ base.name }}</strong>
                <span>{{ base.description || "暂无描述" }}</span>
              </div>
              <div class="kb-actions">
                <el-tag effect="plain">私人</el-tag>
                <el-button link type="primary" @click="openEditDialog(base)">编辑</el-button>
                <el-button
                  link
                  type="danger"
                  :loading="deletingKnowledgeBaseId === base.id"
                  @click="removeKnowledgeBase(base)"
                >
                  删除
                </el-button>
              </div>
            </div>
            <el-empty v-if="!knowledgeBases.length" description="暂无知识库。" />
          </div>
        </article>
      </section>
    </main>

    <el-dialog v-model="editDialogVisible" title="编辑知识库" width="min(520px, 92vw)">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="名称" required>
          <el-input v-model="editForm.name" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="说明这个知识库主要存放什么资料"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="saveKnowledgeBase">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listDocuments } from "../api/documents";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  updateKnowledgeBase,
} from "../api/knowledgeBases";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const router = useRouter();
const userStore = useUserStore();
const healthOnline = ref(false);
const knowledgeBases = ref([]);
const documents = ref([]);
const creating = ref(false);
const updating = ref(false);
const editDialogVisible = ref(false);
const deletingKnowledgeBaseId = ref(null);
const kbForm = reactive({
  name: "",
  description: "",
});
const editForm = reactive({
  id: null,
  name: "",
  description: "",
});

const initials = computed(() => userStore.displayName.slice(0, 1).toUpperCase());

onMounted(() => {
  checkHealth();
  loadData();
});

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadData() {
  try {
    const [bases, docs] = await Promise.all([listKnowledgeBases(), listDocuments()]);
    knowledgeBases.value = bases;
    documents.value = docs;
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function createKb() {
  const name = kbForm.name.trim();
  if (!name) {
    ElMessage.warning("请输入知识库名称。");
    return;
  }

  creating.value = true;
  try {
    await createKnowledgeBase({
      name,
      description: kbForm.description.trim() || null,
      visibility: "private",
    });
    kbForm.name = "";
    kbForm.description = "";
    ElMessage.success("知识库已创建。");
    loadData();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    creating.value = false;
  }
}

async function removeKnowledgeBase(base) {
  try {
    await ElMessageBox.confirm(
      `确定删除知识库“${base.name}”吗？其中的所有文档、文本片段和向量数据都会被删除，且无法恢复。`,
      "确认删除知识库",
      {
        confirmButtonText: "确定删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    deletingKnowledgeBaseId.value = base.id;
    await deleteKnowledgeBase(base.id);
    ElMessage.success("知识库已删除。");
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.message || "删除知识库失败。");
    }
  } finally {
    deletingKnowledgeBaseId.value = null;
  }
}

function openEditDialog(base) {
  editForm.id = base.id;
  editForm.name = base.name;
  editForm.description = base.description || "";
  editDialogVisible.value = true;
}

async function saveKnowledgeBase() {
  const name = editForm.name.trim();
  if (!name) {
    ElMessage.warning("知识库名称不能为空。");
    return;
  }

  updating.value = true;
  try {
    const updated = await updateKnowledgeBase(editForm.id, {
      name,
      description: editForm.description.trim(),
    });
    const index = knowledgeBases.value.findIndex((base) => base.id === updated.id);
    if (index >= 0) {
      knowledgeBases.value[index] = updated;
    }
    editDialogVisible.value = false;
    ElMessage.success("知识库信息已更新。");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    updating.value = false;
  }
}

function goDocuments() {
  router.push({ name: "documents" });
}

function goModelSettings() {
  router.push({ name: "ai-model-settings" });
}

</script>

<style scoped>
.me-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.page {
  width: min(1180px, calc(100% - 32px));
  margin: 44px auto 0;
}

.page-head,
.profile-grid,
.model-settings-entry,
.manager-grid {
  margin-bottom: 20px;
}

.model-settings-entry {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 16px;
  padding: 20px 22px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  color: inherit;
  background: linear-gradient(120deg, var(--cm-surface), var(--cm-primary-soft));
  box-shadow: var(--cm-shadow);
  cursor: pointer;
  text-align: left;
  transition: transform 0.18s ease, border-color 0.18s ease;
}

.model-settings-entry:hover {
  border-color: var(--cm-primary);
  transform: translateY(-2px);
}

.entry-icon {
  display: grid;
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 16px;
  color: #ffffff;
  background: linear-gradient(135deg, var(--cm-primary), #38bdf8);
  font-weight: 900;
}

.entry-copy {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 4px;
}

.entry-copy small {
  color: var(--cm-primary);
  font-weight: 800;
}

.entry-copy strong {
  color: var(--cm-heading);
  font-size: 19px;
}

.entry-copy span,
.entry-action {
  color: var(--cm-muted);
}

.entry-action {
  flex: 0 0 auto;
  font-weight: 700;
}

.page-head,
.profile-panel,
.stat-panel,
.panel-head,
.kb-item {
  display: flex;
  align-items: center;
}

.page-head {
  justify-content: space-between;
  gap: 18px;
}

.page-head h1 {
  margin: 12px 0 8px;
  color: var(--cm-heading);
  font-size: 34px;
}

.page-head p {
  margin: 0;
  color: var(--cm-muted);
  line-height: 1.7;
}

.profile-grid,
.manager-grid {
  display: grid;
  gap: 20px;
}

.profile-grid {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.7fr);
}

.manager-grid {
  grid-template-columns: minmax(300px, 0.75fr) minmax(0, 1fr);
}

.panel {
  padding: 22px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.profile-panel {
  gap: 16px;
}

.profile-panel > div:nth-child(2) {
  min-width: 0;
  flex: 1;
}

.avatar {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: var(--cm-radius);
  color: #ffffff;
  background: linear-gradient(135deg, var(--cm-primary), #38bdf8);
  font-size: 24px;
  font-weight: 900;
}

.profile-panel p,
.panel-head p {
  margin: 0 0 6px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

.profile-panel h2,
.panel-head h2 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 22px;
}

.profile-panel span {
  color: var(--cm-muted);
}

.stat-panel {
  justify-content: space-between;
  gap: 12px;
}

.stat-panel div {
  display: grid;
  gap: 6px;
}

.stat-panel span {
  color: var(--cm-muted);
  font-size: 13px;
}

.stat-panel strong {
  color: var(--cm-heading);
  font-size: 28px;
}

.create-panel,
.list-panel,
.kb-list {
  display: grid;
  gap: 16px;
}

.panel-head {
  justify-content: space-between;
  gap: 16px;
}

.kb-list {
  max-height: 460px;
  overflow: auto;
}

.kb-item {
  justify-content: space-between;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface-soft);
}

.kb-item > div:first-child {
  display: grid;
  gap: 6px;
}

.kb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-item strong {
  color: var(--cm-heading);
}

.kb-item span {
  color: var(--cm-muted);
  font-size: 13px;
}

@media (max-width: 920px) {
  .profile-grid,
  .manager-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .me-view {
    padding-top: 8px;
  }

  .page {
    width: min(100% - 20px, 1180px);
    margin-top: 32px;
  }

  .page-head,
  .profile-panel,
  .stat-panel,
  .panel-head,
  .model-settings-entry {
    align-items: stretch;
    flex-direction: column;
  }

  .entry-action {
    align-self: flex-start;
  }
}
</style>
