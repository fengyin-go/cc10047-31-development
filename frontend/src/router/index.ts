import { createRouter, createWebHistory } from 'vue-router'

import OrphanFilesView from '@/views/OrphanFilesView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 固定路径放在动态模块路由之前，避免 /orphan-files 被当成模块名。
    { path: '/orphan-files', name: 'orphan-files', component: OrphanFilesView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
