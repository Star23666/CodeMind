<template>
  <section class="upload-panel" id="documents">
    <div class="panel-head">
      <div>
        <p>文档上传</p>
        <h2>把资料放进知识库</h2>
      </div>
      <el-tag effect="plain">KB {{ knowledgeBaseId }}</el-tag>
    </div>

    <el-upload
      drag
      :http-request="handleUpload"
      :show-file-list="true"
      :limit="6"
      accept=".pdf,.doc,.docx,.md,.txt"
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
import { ElMessage } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";
import { uploadDocument } from "../../api/documents";

const props = defineProps({
  knowledgeBaseId: {
    type: Number,
    default: 1,
  },
});

const emit = defineEmits(["uploaded"]);
const lastDocument = ref(null);

async function handleUpload(options) {
  try {
    const document = await uploadDocument({
      knowledgeBaseId: props.knowledgeBaseId,
      file: options.file,
    });
    lastDocument.value = document;
    emit("uploaded", document);
    options.onSuccess?.(document);
    ElMessage.success("文件已提交到后端处理");
  } catch (error) {
    options.onError?.(error);
    ElMessage.error(error.message);
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
