<template>
  <div class="app-shell">
    <header class="app-shell__header">
      <span class="app-shell__title">video-strm 任务调度</span>
      <span class="app-shell__subtitle">STRM 生成 · 多服务器 · 实时日志</span>
      <ThemeToggle class="app-shell__theme" />
    </header>
    <main class="app-shell__main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import ThemeToggle from '@/components/ThemeToggle.vue'
</script>

<style scoped lang="scss">
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;

  &__header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 24px;
    background: var(--el-bg-color);
    border-bottom: 1px solid var(--el-border-color-light);
    flex-shrink: 0;
  }

  &__theme {
    margin-left: auto;
  }

  &__title {
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  &__subtitle {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  &__main {
    flex: 1;
    min-height: 0;
    padding: 16px 24px;
    overflow: auto;
  }
}
</style>
