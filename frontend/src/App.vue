<template>
  <main class="app-shell">
    <section class="hero">
      <p class="eyebrow">CodeMind</p>
      <h1>计算机知识 RAG 问答系统</h1>
      <p class="description">
        上传课程资料、技术文档和学习笔记，构建可追溯来源的知识库问答体验。
      </p>
    </section>

    <section class="workspace">
      <div class="panel">
        <h2>文档上传</h2>
        <el-upload drag action="/api/documents/upload" name="file">
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div>拖拽文件到此处，或点击上传</div>
          <template #tip>
            <p class="tip">计划支持 PDF、DOCX、Markdown 和 TXT 文件。</p>
          </template>
        </el-upload>
      </div>

      <div class="panel">
        <h2>知识库问答</h2>
        <el-input
          v-model="question"
          type="textarea"
          :rows="5"
          placeholder="例如：操作系统中的进程和线程有什么区别？"
        />
        <el-button class="ask-button" type="primary" @click="askQuestion">发送问题</el-button>
        <div v-if="answer" class="answer">
          <strong>回答：</strong>
          <p>{{ answer }}</p>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import axios from 'axios'

const question = ref('')
const answer = ref('')

async function askQuestion() {
  if (!question.value.trim()) {
    answer.value = '请先输入问题。'
    return
  }

  const response = await axios.post('/api/chat', {
    question: question.value,
    top_k: 5
  })
  answer.value = response.data.answer
}
</script>

