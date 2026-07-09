import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import App from './App.vue'
import router from './router'

const app=createApp(App)
app.use(ElementPlus)
app.use(createPinia())
app.use(router)
app.mount('#app')

createApp(App).use(router).use(ElementPlus).mount("#app");
