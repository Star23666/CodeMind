<template>
  <div class="auth-view">
    <AppHeader :show-health="false" />

    <main class="auth-page">
      <section class="auth-card">
        <div class="auth-head">
          <el-tag effect="plain">登录</el-tag>
          <h1>进入你的知识库</h1>
          <p>登录后访问自己的知识库、文档和 AI 问答空间。</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="用户名或邮箱" prop="username">
            <el-input v-model="form.username" autocomplete="username" placeholder="请输入用户名或邮箱" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              autocomplete="current-password"
              show-password
              placeholder="请输入密码"
            />
          </el-form-item>
          <el-button type="primary" size="large" :loading="loading" class="submit-button" @click="submit">
            登录
          </el-button>
        </el-form>

        <p class="switch-link">
          还没有账号？
          <RouterLink :to="{ name: 'register', query: route.query }">去注册</RouterLink>
        </p>
      </section>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getCurrentUser, loginUser } from "../api/auth";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const formRef = ref(null);
const loading = ref(false);
const form = reactive({
  username: "",
  password: "",
});

const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function submit() {
  await formRef.value?.validate();
  loading.value = true;
  try {
    const tokenData = await loginUser({
      username: form.username,
      password: form.password,
    });

    userStore.setAuth({ token: tokenData.access_token, user: null });
    userStore.updateUser(await getCurrentUser());
    ElMessage.success("登录成功。");
    router.replace(resolveRedirect());
  } catch (error) {
    userStore.clearAuth();
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function resolveRedirect() {
  const redirect = route.query.redirect;
  return typeof redirect === "string" && redirect.startsWith("/") && !redirect.startsWith("//")
    ? redirect
    : "/";
}
</script>

<style scoped>
.auth-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.auth-page {
  display: grid;
  min-height: calc(100vh - 140px);
  place-items: center;
  width: min(100% - 32px, 1180px);
  margin: 0 auto;
}

.auth-card {
  display: grid;
  gap: 22px;
  width: min(430px, 100%);
  padding: 28px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.auth-head {
  display: grid;
  gap: 10px;
  text-align: center;
}

.auth-head :deep(.el-tag) {
  justify-self: center;
}

h1 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 30px;
}

p {
  margin: 0;
  color: var(--cm-muted);
  line-height: 1.7;
}

.submit-button {
  width: 100%;
}

.switch-link {
  text-align: center;
}

.switch-link a {
  color: var(--cm-primary);
  font-weight: 800;
}

@media (max-width: 640px) {
  .auth-view {
    padding-top: 8px;
  }
}
</style>
