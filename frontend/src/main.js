import { createApp } from 'vue'
import './styles/base.css'
import App from './App.vue'
import { router } from './router'
import { getCurrentUser } from './api/auth'
import { setUnauthorizedHandler } from './api/request'
import { useUserStore } from './stores/user'

localStorage.removeItem('codemind-theme')
document.documentElement.dataset.theme = 'light'

const app = createApp(App)
const userStore = useUserStore()

async function bootstrap() {
  if (userStore.token) {
    try {
      userStore.updateUser(await getCurrentUser())
    } catch {
      userStore.clearAuth()
    }
  }

  setUnauthorizedHandler(() => {
    const currentRoute = router.currentRoute.value
    const isAuthPage = currentRoute.name === 'login' || currentRoute.name === 'register'
    const redirect = isAuthPage ? undefined : currentRoute.fullPath
    userStore.clearAuth()

    if (!isAuthPage) {
      router.replace({
        name: 'login',
        query: redirect ? { redirect } : {},
      })
    }
  })

  app.use(router)
  await router.isReady()
  app.mount('#app')
}

bootstrap()
