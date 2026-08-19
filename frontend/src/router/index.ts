import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'OpenList',
      component: () => import('@/views/OpenList/index.vue'),
      meta: { title: '任务调度' }
    }
  ]
})

export default router
