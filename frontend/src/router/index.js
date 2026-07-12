import { createRouter, createWebHistory } from "vue-router";
import { useUserStore } from "../stores/user";

const routes = [
  {
    path: "/",
    name: "home",
    component: () => import("../views/HomeView.vue"),
  },
  {
    path: "/documents",
    name: "documents",
    component: () => import("../views/DocumentUploadView.vue"),
  },
  {
    path: "/documents/:documentId",
    name: "document-detail",
    component: () => import("../views/DocumentDetailView.vue"),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: "/documents/:documentId/chunks/:chunkId",
    name: "document-chunk",
    component: () => import("../views/DocumentDetailView.vue"),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: "/library",
    name: "document-library",
    component: () => import("../views/DocumentLibraryView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/documents/:documentId/view",
    name: "document-viewer",
    component: () => import("../views/DocumentViewerView.vue"),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: "/history",
    name: "qa-history",
    component: () => import("../views/QaHistoryView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/me",
    name: "me",
    component: () => import("../views/MeView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { guestOnly: true },
  },
  {
    path: "/register",
    name: "register",
    component: () => import("../views/RegisterView.vue"),
    meta: { guestOnly: true },
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/",
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const userStore = useUserStore();

  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    return {
      name: "login",
      query: { redirect: to.fullPath },
    };
  }

  if (to.meta.guestOnly && userStore.isLoggedIn) {
    return { name: "home" };
  }

  return true;
});
