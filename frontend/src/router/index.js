import { createRouter, createWebHistory } from "vue-router";

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
  },
  {
    path: "/documents/:documentId/chunks/:chunkId",
    name: "document-chunk",
    component: () => import("../views/DocumentDetailView.vue"),
    props: true,
  },
  {
    path: "/me",
    name: "me",
    component: () => import("../views/MeView.vue"),
  },
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
  },
  {
    path: "/register",
    name: "register",
    component: () => import("../views/RegisterView.vue"),
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
