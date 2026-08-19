<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'

import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListExecution, WsFrame, WsStatusFrame } from '@/types/openlist'
import { connectWs, disconnectWs, wsState, type WsState } from '@/utils/ws'

const store = useOpenlistStore()

const selectedExecutionId = ref<number | null>(null)
const ws = ref<WebSocket | null>(null)
const connState = ref<WsState>('disconnected')
const logLines = ref<Array<{ ts: string; level: string; message: string }>>([])
const progress = ref({ totalVideos: 0, successVideos: 0, totalSubtitles: 0, successSubtitles: 0 })
const statusFrame = ref<WsStatusFrame | null>(null)
// 自动滚动开关：开启时新日志到达自动滚到底部；关闭时停留在当前查看位置
const autoScroll = ref(true)
// 待启动标记：连接成功后自动启动该执行（先连日志再执行）
const pendingStart = ref<{ executionId: number; taskId: number; serverId: number } | null>(null)
const launching = ref(false)
// 本次批量执行的任务列表（多个 execution）：默认展示第一个，可切换查看其他
const batchExecutions = ref<Array<{ executionId: number; taskId: number; taskName: string }>>([])
// 本次批量执行使用的服务器 ID
const batchServerId = ref<number | null>(null)

const logContainer = ref<HTMLElement | null>(null)

const runningExecutions = computed(() => store.runningExecutions)
const executionOptions = computed(() => {
  // 优先展示本次批量执行的任务列表；否则回退到正在执行的记录
  if (batchExecutions.value.length > 0) {
    return batchExecutions.value.map(b => ({
      id: b.executionId,
      task_name: b.taskName
    }))
  }
  const ids = new Set(store.runningExecutions.map(e => e.id))
  const selected = selectedExecutionId.value
  const rows = [...store.runningExecutions]
  if (selected != null && !ids.has(selected)) {
    const placeholder: OpenListExecution = {
      id: selected,
      task_id: 0,
      task_name: `执行 #${selected}`,
      server_id: null,
      server_name: null,
      status: 'success',
      video_success_count: 0,
      video_total_count: 0,
      subtitle_success_count: 0,
      subtitle_total_count: 0,
      is_incremental: true,
      is_force: false,
      duration_seconds: null,
      log_path: null,
      started_time: null,
      finished_time: null,
      created_time: null
    }
    rows.push(placeholder)
  }
  return rows
})

function handleFrame(frame: WsFrame) {
  if (frame.type === 'log') {
    logLines.value.push({ ts: frame.ts, level: frame.level, message: frame.message })
    if (logLines.value.length > 3000) {
      logLines.value.splice(0, logLines.value.length - 3000)
    }
    if (autoScroll.value) {
      scrollToBottom()
    }
  } else if (frame.type === 'progress') {
    progress.value = { ...progress.value, ...frame.data }
  } else if (frame.type === 'status') {
    statusFrame.value = frame
    progress.value = {
      totalVideos: frame.video_total_count,
      successVideos: frame.video_success_count,
      totalSubtitles: frame.subtitle_total_count,
      successSubtitles: frame.subtitle_success_count
    }
    store.fetchRunning()
    // 当前执行已结束：从下拉移除，提示前往任务历史查看日志
    const finished = selectedExecutionId.value
    if (finished != null) {
      removeFromBatch(finished)
      disconnectWs(ws.value)
      ws.value = null
      connState.value = 'disconnected'
      pendingStart.value = null
      ElMessage.info('任务执行完成，前往「任务历史」查看日志')
    }
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = logContainer.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

function handleScroll() {
  const el = logContainer.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 20
  // 用户手动向上滚动浏览历史时，自动关闭自动滚动；滚回底部不影响开关状态
  if (autoScroll.value && !atBottom) {
    autoScroll.value = false
  }
}

function handleConnect() {
  if (selectedExecutionId.value == null) {
    return
  }
  disconnectWs(ws.value)
  logLines.value = []
  statusFrame.value = null
  connState.value = 'connecting'
  ws.value = connectWs(selectedExecutionId.value, {
    onOpen: () => {
      connState.value = 'connected'
      // 先连日志后执行：连接成功后才启动后台任务，保证不漏日志
      if (pendingStart.value) {
        launchPending()
      }
    },
    onMessage: handleFrame,
    onClose: () => {
      connState.value = 'disconnected'
    },
    onError: () => {
      connState.value = 'disconnected'
    }
  })
}

async function launchPending() {
  const pending = pendingStart.value
  if (!pending || launching.value) return
  launching.value = true
  try {
    await store.startExecution({
      execution_id: pending.executionId,
      task_id: pending.taskId,
      server_id: pending.serverId
    })
    pendingStart.value = null
    store.fetchRunning()
  } catch {
    // 启动失败：保留 pending 以允许手动重试
    ElMessage.error('任务启动失败，请检查配置后重试')
  } finally {
    launching.value = false
  }
}

/**
 * 供执行管理页调用：传入批量执行的 execution 列表（含 task_id）与服务器 ID，
 * 默认连接第一个并启动。
 */
function setExecutions(
  executions: Array<{ executionId: number; taskId: number; taskName: string }>,
  serverId?: number
) {
  batchExecutions.value = executions
  batchServerId.value = serverId ?? null
  const first = executions[0]
  if (!first) return
  startAndConnect(first.executionId, first.taskId, serverId ?? 0)
}

/**
 * 供执行管理页调用：选中该执行、连接日志，连接成功后自动启动。
 */
async function startAndConnect(executionId: number, taskId: number, serverId: number = 0) {
  await store.fetchRunning()
  selectedExecutionId.value = executionId
  pendingStart.value = { executionId, taskId, serverId }
  handleConnect()
}

function handleDisconnect() {
  disconnectWs(ws.value)
  ws.value = null
  connState.value = 'disconnected'
  pendingStart.value = null
}

/** 判断某执行记录是否仍在运行中（runningExecutions 含该 id 才算）。 */
function isStillRunning(executionId: number): boolean {
  return store.runningExecutions.some(e => e.id === executionId)
}

/** 从本次批量执行列表中移除已完成的执行，刷新下拉数据；列表清空则重置选择。 */
function removeFromBatch(executionId: number) {
  batchExecutions.value = batchExecutions.value.filter(b => b.executionId !== executionId)
  if (batchExecutions.value.length === 0) {
    selectedExecutionId.value = null
  }
}

function handleExecutionChange() {
  handleDisconnect()
  const selected = selectedExecutionId.value
  if (selected == null) return

  // 任务已完成（不在运行中）：提示前往任务历史，不连接/不启动，并刷新下拉
  if (!isStillRunning(selected)) {
    removeFromBatch(selected)
    store.fetchRunning()
    ElMessage.info('任务执行完成，前往「任务历史」查看日志')
    return
  }

  // 仍在运行：切换查看，连接后若尚未启动则自动启动
  // 优先取本次批量执行列表中的 taskId；不在批量列表时从运行中记录取真实 task_id/server_id，
  // 避免手动切换其他正在执行的任务时 taskId 回退为 0，触发后端"执行记录与任务不匹配"（BUG-2）
  const batchItem = batchExecutions.value.find(b => b.executionId === selected)
  const runningItem = store.runningExecutions.find(e => e.id === selected)
  const taskId = batchItem?.taskId ?? runningItem?.task_id
  if (!taskId) {
    ElMessage.error('未找到该执行记录对应的任务，请刷新后重试')
    return
  }
  const serverId = batchServerId.value ?? runningItem?.server_id ?? 0
  startAndConnect(selected, taskId, serverId)
}

const CONN_LABEL: Record<WsState, string> = {
  connecting: '连接中',
  connected: '已连接',
  disconnected: '未连接'
}
const CONN_TAG: Record<WsState, 'info' | 'success' | 'danger'> = {
  connecting: 'info',
  connected: 'success',
  disconnected: 'danger'
}

const videoPercent = computed(() => {
  const { totalVideos, successVideos } = progress.value
  return totalVideos > 0 ? Math.round((successVideos / totalVideos) * 100) : 0
})
const subtitlePercent = computed(() => {
  const { totalSubtitles, successSubtitles } = progress.value
  return totalSubtitles > 0 ? Math.round((successSubtitles / totalSubtitles) * 100) : 0
})

onMounted(() => {
  store.fetchRunning()
})

onUnmounted(() => {
  handleDisconnect()
})

defineExpose({
  reload: () => {
    store.fetchRunning()
  },
  startAndConnect,
  setExecutions
})
</script>

<template>
  <div class="realtime-log">
    <el-card shadow="never" class="realtime-log__card">
      <template #header>
        <div class="realtime-log__header">
          <span>实时日志</span>
          <div class="realtime-log__controls">
            <el-select v-model="selectedExecutionId" placeholder="选择执行记录" class="realtime-log__select"
              @change="handleExecutionChange">
              <el-option v-for="ex in executionOptions" :key="ex.id" :label="ex.task_name" :value="ex.id" />
            </el-select>
            <el-tag :type="CONN_TAG[connState]" effect="light">{{ CONN_LABEL[connState] }}</el-tag>
            <el-button v-if="connState !== 'connected'" type="primary" :icon="VideoPlay"
              :disabled="selectedExecutionId == null" @click="handleConnect">
              连接
            </el-button>
            <el-button v-else type="warning" :icon="VideoPause" @click="handleDisconnect">
              断开
            </el-button>
            <el-switch v-model="autoScroll" inline-prompt size="small" class="realtime-log__autoscroll" />
          </div>
        </div>
      </template>

      <div class="realtime-log__progress">
        <div class="realtime-log__progress-item">
          <span class="realtime-log__progress-label">视频</span>
          <el-progress :percentage="videoPercent" :stroke-width="12" :status="videoPercent === 100 ? 'success' : ''">
            <span class="realtime-log__progress-text">{{ progress.successVideos }}/{{ progress.totalVideos }}</span>
          </el-progress>
        </div>
        <div class="realtime-log__progress-item">
          <span class="realtime-log__progress-label">字幕</span>
          <el-progress :percentage="subtitlePercent" :stroke-width="12"
            :status="subtitlePercent === 100 ? 'success' : ''">
            <span class="realtime-log__progress-text">{{ progress.successSubtitles }}/{{ progress.totalSubtitles
              }}</span>
          </el-progress>
        </div>
      </div>

      <div class="realtime-log__console-wrap">
        <div ref="logContainer" class="realtime-log__console" @scroll="handleScroll">
          <template v-if="logLines.length">
            <div v-for="(line, index) in logLines" :key="index" class="realtime-log__line"
              :class="`realtime-log__line--${line.level}`">
              <span class="realtime-log__time">{{ line.ts }}</span>
              <span class="realtime-log__level">{{ line.level.toUpperCase() }}</span>
              <span class="realtime-log__message">{{ line.message }}</span>
            </div>
          </template>
          <el-empty v-else description="暂无日志，点击「连接」开始接收" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.realtime-log {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;

  &__card {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;

    :deep(.el-card__body) {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__select {
    width: 220px;
  }

  &__autoscroll {
    margin-left: 4px;
    flex-shrink: 0;
  }

  &__progress {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-bottom: 12px;
  }

  &__progress-item {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__progress-label {
    width: 36px;
    flex-shrink: 0;
    font-size: var(--el-font-size-small);
    color: var(--el-text-color-regular);
  }

  &__progress-text {
    font-size: var(--el-font-size-extra-small);
  }

  &__console-wrap {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  &__console {
    height: 100%;
    overflow-y: auto;
    background: #1e1e1e;
    border-radius: 4px;
    padding: 12px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.7;
  }

  &__line {
    display: flex;
    gap: 8px;
    white-space: pre-wrap;
    word-break: break-all;

    &--info {
      color: #d4d4d4;
    }

    &--warn {
      color: #e6a23c;
    }

    &--error {
      color: #f56c6c;
    }

    &--progress {
      color: #409eff;
    }
  }

  &__time {
    color: #6a9955;
    flex-shrink: 0;
  }

  &__level {
    color: #569cd6;
    flex-shrink: 0;
  }

  &__message {
    color: inherit;
  }
}
</style>
