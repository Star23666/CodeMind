<template>
  <section class="upload-panel" id="documents">
    <div class="panel-head">
      <div>
        <p>文档上传</p>
        <h2>把资料放进知识库</h2>
      </div>
    </div>

    <el-upload
      drag
      :http-request="handleUpload"
      :show-file-list="true"
      :limit="6"
      accept=".pdf,.docx,.md,.markdown,.txt"
    >
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-text">拖拽文件到此处，或点击选择上传</div>
      <template #tip>
        <p class="tip">支持 PDF、Word、Markdown、TXT。上传后后端会自动解析、切分并写入向量库。</p>
      </template>
    </el-upload>

    <div v-if="lastDocument" class="upload-result">
      <strong>{{ lastDocument.file_name }}</strong>
      <span>{{ lastDocument.parse_status }} · {{ lastDocument.file_type }}</span>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { UploadFilled } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import { uploadDocument } from "../../api/documents";
import { useUserStore } from "../../stores/user";

const props = defineProps({
  knowledgeBaseId: {
    type: Number,
    default: null,
  },
});

const router = useRouter();
const userStore = useUserStore();
const emit = defineEmits(["uploaded"]);
const lastDocument = ref(null);

async function handleUpload(options) {
  if (!userStore.isLoggedIn) {
    options.onError?.(new Error("请先登录。"));
    router.push({ name: "login", query: { redirect: "/documents" } });
    return;
  }

  if (!props.knowledgeBaseId) {
    options.onError?.(new Error("请先创建知识库。"));
    try {
      await ElMessageBox.confirm(
        "请先创建一个知识库，再上传文档。",
        "创建一个知识库",
        {
          confirmButtonText: "去创建",
          cancelButtonText: "取消",
          type: "warning",
        },
      );
      router.push({ name: "me" });
    } catch {
      // 用户取消后留在当前页面。
    }
    return;
  }

  try {
    const document = await uploadDocument({
      knowledgeBaseId: props.knowledgeBaseId,
      file: options.file,
      onUploadProgress: (event) => {
        if (!event.total) return;
        const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
        options.onProgress?.({ percent });
      },
    });
    lastDocument.value = document;
    emit("uploaded", document);
    options.onSuccess?.(document);
    ElMessage.success("文件已提交到后端处理");
  } catch (error) {
    options.onError?.(error);
    const message = /timeout|超时/i.test(error.message)
      ? "上传响应超时，请先到文档库确认是否已经上传成功，避免重复提交。"
      : error.message;
    ElMessage.error(message);
  }
}
</script>

<style scoped>
.upload-panel {
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel-head p {
  margin: 0 0 6px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

h2 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 22px;
}

.upload-icon {
  margin-bottom: 10px;
  color: var(--cm-primary);
  font-size: 46px;
}

.upload-text {
  color: var(--cm-heading);
  font-weight: 800;
}

.tip {
  margin: 8px 0 0;
  color: var(--cm-muted);
}

.upload-result {
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface-soft);
}

.upload-result strong {
  color: var(--cm-heading);
}

.upload-result span {
  color: var(--cm-muted);
  font-size: 13px;
}

@media (max-width: 700px) {
  .panel-head {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
