import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('./views/ChildChat.vue'),
      meta: { title: '小思陪练' },
    },
    {
      path: '/parent',
      component: () => import('./views/ParentPanel.vue'),
      meta: { title: '家长设置' },
    },
  ],
})

export default router
