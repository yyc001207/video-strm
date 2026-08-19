<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay } from '@element-plus/icons-vue'

import { useOpenlistStore } from '@/stores/openlist'

const emit = defineEmits<{ (e: 'navigate', tab: string, payload?: Record<string, unknown>): void }>()

const store = useOpenlistStore()

const selectedServerId = ref<number | null>(null)
const selectedTaskIds = ref<number[]>([])
const isIncremental = ref(true)
const isForce = ref(false)
const strmOnly = ref(false)
const starting = ref(false)
const cancelling = ref(false)
const loading = ref(false)

const serverOptions = computed(() => store.servers.filter(s => s.is_active))
const taskOptions = computed(() => store.tasks)

const canStart = computed(
  () => selectedServerId.value != null && selectedTaskIds.value.length > 0
)

// 关闭「强制生成」时自动重置「仅更新 strm」为关闭
watch(isForce, v => {
  if (!v) strmOnly.value = false
})

async function load() {
  loading.value = true
  try {
    await Promise.all([store.fetchConfig(), store.fetchTasks(), store.fetchRunning()])
    if (selectedServerId.value == null && serverOptions.value.length > 0) {
      selectedServerId.value = serverOptions.value[0].id
    }
  } finally {
    loading.value = false
  }
}

async function handleStart() {
  if (selectedServerId.value == null) {
    ElMessage.warning('请先选择服务器')
    return
  }
  if (selectedTaskIds.value.length === 0) {
    ElMessage.warning('请至少选择一个任务')
    return
  }
  starting.value = true
  try {
    // 批量创建执行记录（仅落库，不启动），返回全部 execution
    const executions = await store.batchCreateExecution(
      selectedServerId.value,
      selectedTaskIds.value.map(id => ({
        task_id: id,
        is_incremental: isIncremental.value,
        is_force: isForce.value,
        strm_only: strmOnly.value
      }))
    )
    // 跳转实时日志页：默认展示第一个任务的日志，可切换查看其他
    const taskNameMap = new Map(store.tasks.map(t => [t.id, t.name]))
    emit('navigate', 'realtime', {
      executionIds: executions.map(e => e.id),
      taskIds: executions.map(e => e.task_id),
      taskNames: executions.map(e => taskNameMap.get(e.task_id) ?? `任务 #${e.task_id}`),
      serverId: selectedServerId.value
    })
  } catch {
    /* 拦截器提示 */
  } finally {
    starting.value = false
  }
}

async function handleCancel() {
  const running = store.runningExecutions.find(e => selectedTaskIds.value.includes(e.task_id))
  if (!running) {
    ElMessage.info('当前没有正在执行的任务')
    return
  }
  try {
    await ElMessageBox.confirm('确认取消当前执行？', '提示', { type: 'warning' })
  } catch {
    return
  }
  cancelling.value = true
  try {
    await store.cancelExecution(running.id)
    ElMessage.success('已请求取消')
  } catch {
    /* 拦截器提示 */
  } finally {
    cancelling.value = false
  }
}

const STATUS_LABEL: Record<string, string> = {
  running: '执行中',
  success: '成功',
  fail: '失败',
  cancelled: '已取消'
}

const STATUS_TAG: Record<string, 'primary' | 'success' | 'danger' | 'info'> = {
  running: 'primary',
  success: 'success',
  fail: 'danger',
  cancelled: 'info'
}

onMounted(() => {
  load()
  const timer = setInterval(() => {
    if (store.runningExecutions.length > 0) {
      store.fetchRunning()
    }
  }, 5000)
  return () => clearInterval(timer)
})

defineExpose({ reload: load })
</script>

<template>
  <div class="execution">
    <el-card shadow="never" class="execution__card">
      <template #header>
        <div class="execution__header">
          <span>执行管理</span>
          <el-button link type="primary" @click="load">刷新</el-button>
        </div>
      </template>

      <div class="execution__form">
        <el-form label-width="90px" class="execution__panel">
          <el-form-item label="选择服务器">
            <el-select v-model="selectedServerId" placeholder="请选择服务器配置" class="execution__select">
              <el-option
                v-for="server in serverOptions"
                :key="server.id"
                :label="server.name || server.server_url"
                :value="server.id"
              />
            </el-select>
            <span v-if="!serverOptions.length" class="execution__hint">请先在「全局配置」新增服务器</span>
          </el-form-item>
          <el-form-item label="选择任务">
            <el-select
              v-model="selectedTaskIds"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="可选择多个任务配置"
              class="execution__select"
              clearable
            >
              <el-option
                v-for="task in taskOptions"
                :key="task.id"
                :label="task.name"
                :value="task.id"
                :disabled="store.runningTaskIds.has(task.id)"
              />
            </el-select>
            <span class="execution__hint">可多选，将依次在所选服务器上执行</span>
          </el-form-item>
          <el-form-item label="增量更新">
            <el-switch v-model="isIncremental" />
            <span class="execution__hint">默认开启，跳过已存在的 STRM/字幕</span>
          </el-form-item>
          <el-form-item label="强制生成">
            <el-switch v-model="isForce" />
            <span class="execution__hint">默认关闭，开启则重新生成全部</span>
          </el-form-item>
          <el-form-item v-if="isForce" label="仅更新 strm">
            <el-switch v-model="strmOnly" />
            <span class="execution__hint">开启后只更新 strm，不重新下载已存在的字幕</span>
          </el-form-item>
          <el-form-item>
            <div class="execution__actions">
              <el-button
                type="primary"
                :icon="VideoPlay"
                :loading="starting"
                :disabled="!canStart"
                @click="handleStart"
              >
                执行任务
              </el-button>
              <el-button
                type="warning"
                :loading="cancelling"
                :disabled="!store.runningExecutions.some(e => selectedTaskIds.includes(e.task_id))"
                @click="handleCancel"
              >
                取消任务
              </el-button>
            </div>
          </el-form-item>
        </el-form>
      </div>
    </el-card>

    <el-card shadow="never" class="execution__list">
      <template #header>
        <span>正在执行</span>
      </template>
      <el-table v-loading="loading" :data="store.runningExecutions" row-key="id" height="100%" class="execution__table">
        <el-table-column label="任务" prop="task_name" min-width="140" show-overflow-tooltip />
        <el-table-column label="服务器" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.server_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status] ?? 'info'" effect="light">
              {{ STATUS_LABEL[row.status] ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="视频" width="110">
          <template #default="{ row }">
            {{ row.video_success_count }}/{{ row.video_total_count }}
          </template>
        </el-table-column>
        <el-table-column label="字幕" width="110">
          <template #default="{ row }">
            {{ row.subtitle_success_count }}/{{ row.subtitle_total_count }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="warning" @click="store.cancelExecution(row.id).then(() => ElMessage.success('已请求取消'))">
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.execution {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
  overflow: hidden;

  &__card {
    flex-shrink: 0;

    :deep(.el-card__body) {
      padding-bottom: 0;
    }
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__panel {
    max-width: 720px;
  }

  &__select {
    width: 340px;
  }

  &__hint {
    margin-left: 12px;
    font-size: var(--el-font-size-extra-small);
    color: var(--el-text-color-secondary);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__list {
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

  &__table {
    flex: 1;
    min-height: 0;
  }
}
</style>
