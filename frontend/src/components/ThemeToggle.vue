<script setup lang="ts">
import { computed } from 'vue'
import { Check, Monitor, Moon, Sunny } from '@element-plus/icons-vue'

import { useThemeStore, type ThemeMode } from '@/stores/theme'

const theme = useThemeStore()

const options: Array<{ value: ThemeMode; label: string; icon: typeof Sunny }> = [
  { value: 'light', label: '浅色模式', icon: Sunny },
  { value: 'dark', label: '深色模式', icon: Moon },
  { value: 'auto', label: '跟随系统', icon: Monitor }
]

/** 当前生效主题对应的图标（auto 时显示系统侧图标）。 */
const currentIcon = computed(() => {
  if (theme.isDark) return Moon
  return Sunny
})

function handleCommand(value: ThemeMode | string | number | object) {
  theme.setMode(value as ThemeMode)
}
</script>

<template>
  <el-tooltip :content="`切换主题（当前：${theme.isDark ? '深色' : '浅色'}）`" placement="bottom">
    <el-dropdown trigger="click" @command="handleCommand">
      <button class="theme-toggle" type="button" aria-label="切换主题">
        <el-icon :size="18"><component :is="currentIcon" /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="opt in options"
            :key="opt.value"
            :command="opt.value"
            :class="{ 'theme-toggle__item--active': theme.mode === opt.value }"
          >
            <el-icon class="theme-toggle__item-icon"><component :is="opt.icon" /></el-icon>
            <span class="theme-toggle__item-label">{{ opt.label }}</span>
            <el-icon v-if="theme.mode === opt.value" class="theme-toggle__item-check">
              <Check />
            </el-icon>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </el-tooltip>
</template>

<style scoped lang="scss">
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition:
    border-color 0.2s,
    color 0.2s;

  &:hover {
    border-color: var(--el-color-primary);
    color: var(--el-color-primary);
  }

  &__item-icon {
    margin-right: 6px;
  }

  &__item-label {
    flex: 1;
  }

  &__item-check {
    margin-left: 8px;
    color: var(--el-color-primary);
  }

  :deep(.theme-toggle__item--active) {
    color: var(--el-color-primary);
    font-weight: 600;
  }
}
</style>
