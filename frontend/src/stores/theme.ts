/** 主题状态：浅色 / 深色 / 跟随系统，持久化到 localStorage，切换时同步 html.dark 类。 */

import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

const STORAGE_KEY = 'video-strm-theme'
const VALID_MODES: ThemeMode[] = ['light', 'dark', 'auto']

function readStoredMode(): ThemeMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return VALID_MODES.includes(raw as ThemeMode) ? (raw as ThemeMode) : 'auto'
  } catch {
    return 'auto'
  }
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(readStoredMode())
  const systemDark = ref(false)

  if (window.matchMedia) {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    systemDark.value = media.matches
    media.addEventListener('change', (e) => {
      systemDark.value = e.matches
    })
  }

  /** 当前生效的是否为深色（auto 模式跟随系统）。 */
  const isDark = computed(() => mode.value === 'dark' || (mode.value === 'auto' && systemDark.value))

  /** 把当前状态同步到 <html>（Element Plus 暗黑模式依赖 html.dark 类）。 */
  function apply() {
    document.documentElement.classList.toggle('dark', isDark.value)
    try {
      localStorage.setItem(STORAGE_KEY, mode.value)
    } catch {
      // 忽略隐私模式等场景下的写入失败
    }
  }

  function setMode(next: ThemeMode) {
    mode.value = next
  }

  /** 黑白一键切换：从当前生效主题切到另一侧。 */
  function toggle() {
    mode.value = isDark.value ? 'light' : 'dark'
  }

  watch([mode, systemDark], apply, { immediate: true })

  return { mode, isDark, setMode, toggle }
})
