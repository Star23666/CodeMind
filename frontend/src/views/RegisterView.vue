<template>
  <div class="auth-view">
    <AppHeader :show-health="false" />

    <main class="auth-page">
      <section class="auth-card">
        <div class="auth-head">
          <el-tag effect="plain">注册</el-tag>
          <h1>创建个人知识库账号</h1>
          <p>注册后进入自己的资料空间，后续每个用户只查看自己的知识库。</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" autocomplete="username" placeholder="至少 3 个字符" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="form.email" autocomplete="email" placeholder="用于后续找回账号" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              autocomplete="new-password"
              show-password
              placeholder="至少 8 位"
            />
          </el-form-item>
          <el-button type="primary" size="large" :loading="loading" class="submit-button" @click="submit">
            注册并进入
          </el-button>
        </el-form>

        <p class="switch-link">
          已有账号？
          <RouterLink :to="{ name: 'login', query: route.query }">去登录</RouterLink>
        </p>
      </section>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import { loginUser, registerUser } from "../api/auth";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const formRef = ref(null);
const loading = ref(false);
const form = reactive({
  username: "",
  email: "",
  password: "",
});

const rules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { min: 3, message: "用户名至少 3 个字符", trigger: "blur" },
  ],
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" },
  ],
};

async function submit() {
  await formRef.value?.validate();
  loading.value = true;
  try {
    const user = await registerUser({
      username: form.username,
      email: form.email,
      password: form.password,
    });
    const tokenData = await loginUser({
      username: form.username,
      password: form.password,
    });

    userStore.setAuth({
      token: tokenData.access_token,
      user,
    });
    ElMessage.success("注册成功。");
    router.replace(resolveRedirect());
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function resolveRedirect() {
  const redirect = route.query.redirect;
  return typeof redirect === "string" ? redirect : "/";
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
