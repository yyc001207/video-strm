<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, Download, View } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { useOpenlistStore } from '@/stores/openlist'
import type { HistorySummaryItem, OpenListExecution, OpenListLog } from '@/types/openlist'
import { formatDateTime } from '@/utils/date'

const store = useOpenlistStore()

const list = ref<HistorySummaryItem[]>([])
const loading = ref(false)
const serverFilter = ref<number | null>(null)

/** 视图切换：列表 ↔ 详情（详情作为页面展示，不再使用抽屉）。 */
const viewMode = ref<'list' | 'detail'>('list')
const detailTaskId = ref<number | null>(null)
const detailTaskName = ref('')
const executions = ref<OpenListExecution[]>([])
const detailLoading = ref(false)
const detailPage = ref(1)
const detailTotal = ref(0)
const PAGE_SIZE = 20

const logVisible = ref(false)
const logLoading = ref(false)
const logs = ref<OpenListLog[]>([])
const logExecution = ref<OpenListExecution | null>(null)

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

function durationText(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${sec} 秒`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m} 分 ${s} 秒`
}

async function load() {
  loading.value = true
  try {
    const res = await openlistApi.historySummary(serverFilter.value)
    list.value = res.data.list
  } finally {
    loading.value = false
  }
}

/** 进入详情页面。 */
async function openDetail(item: HistorySummaryItem) {
  detailTaskId.value = item.task_id
  detailTaskName.value = item.task_name
  detailPage.value = 1
  viewMode.value = 'detail'
  await loadDetail()
}

/** 返回列表页面。 */
function backToList() {
  viewMode.value = 'list'
}

async function loadDetail() {
  if (detailTaskId.value == null) return
  detailLoading.value = true
  try {
    const res = await openlistApi.historyByTask(detailTaskId.value, detailPage.value, PAGE_SIZE)
    executions.value = res.data.list
    detailTotal.value = res.total ?? 0
  } finally {
    detailLoading.value = false
  }
}

function handleDetailPageChange() {
  loadDetail()
}

async function openLogs(row: OpenListExecution) {
  logExecution.value = row
  logVisible.value = true
  logLoading.value = true
  logs.value = []
  try {
    const res = await openlistApi.listExecutionLogs(row.id, 1, 500)
    logs.value = res.data.list
  } finally {
    logLoading.value = false
  }
}

function handleDownloadLog(row: OpenListExecution) {
  openlistApi.downloadLog(row.id).catch(() => {
    /* 拦截器提示 */
  })
}

onMounted(async () => {
  await Promise.all([load(), store.fetchConfig()])
})

defineExpose({ reload: load })
</script>

<template>
  <div class="task-history">
    <!-- 列表页面 -->
    <el-card v-if="viewMode === 'list'" shadow="never" class="task-history__card">
      <template #header>
        <div class="task-history__header">
          <span>任务历史（每个任务最近一次执行）</span>
          <el-select
            v-model="serverFilter"
            placeholder="全部服务器"
            clearable
            class="task-history__server-filter"
            @change="load"
          >
            <el-option
              v-for="server in store.servers"
              :key="server.id"
              :label="server.name || server.server_url"
              :value="server.id"
            />
          </el-select>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" row-key="task_id" height="100%" class="task-history__table">
        <el-table-column label="任务名称" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.task_name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="处理路径" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.process_path || '—' }}</template>
        </el-table-column>
        <el-table-column label="服务器" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.execution?.server_name || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="执行状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.execution" :type="STATUS_TAG[row.execution.status] ?? 'info'" effect="light">
              {{ STATUS_LABEL[row.execution.status] ?? row.execution.status }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="视频" width="120">
          <template #default="{ row }">
            <template v-if="row.execution">
              {{ row.execution.video_success_count }}/{{ row.execution.video_total_count }}
            </template>
            <template v-else>—</template>
          </template>
        </el-table-column>
        <el-table-column label="字幕" width="120">
          <template #default="{ row }">
            <template v-if="row.execution">
              {{ row.execution.subtitle_success_count }}/{{ row.execution.subtitle_total_count }}
            </template>
            <template v-else>—</template>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            {{ row.execution ? durationText(row.execution.duration_seconds) : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="170">
          <template #default="{ row }">
            {{ row.execution ? formatDateTime(row.execution.started_time) : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="!row.execution" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 详情页面（替代原抽屉） -->
    <el-card v-else shadow="never" class="task-history__card">
      <template #header>
        <div class="task-history__header">
          <span class="task-history__back">
            <el-button link type="primary" :icon="ArrowLeft" @click="backToList">返回</el-button>
            <span>{{ detailTaskName }} · 执行历史</span>
          </span>
        </div>
      </template>

      <el-table v-loading="detailLoading" :data="executions" row-key="id" height="100%" class="task-history__table">
        <el-table-column label="编号" prop="id" width="80" />
        <el-table-column label="处理路径" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.process_path || '—' }}</template>
        </el-table-column>
        <el-table-column label="输出目录" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.output_dir || '—' }}</template>
        </el-table-column>
        <el-table-column label="服务器" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.server_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status] ?? 'info'" effect="light">
              {{ STATUS_LABEL[row.status] ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="视频" width="120">
          <template #default="{ row }">{{ row.video_success_count }}/{{ row.video_total_count }}</template>
        </el-table-column>
        <el-table-column label="字幕" width="100">
          <template #default="{ row }">{{ row.subtitle_success_count }}/{{ row.subtitle_total_count }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="120">
          <template #default="{ row }">{{ durationText(row.duration_seconds) }}</template>
        </el-table-column>
        <el-table-column label="执行时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.started_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :icon="View" @click="openLogs(row)">日志</el-button>
            <el-button link type="primary" :icon="Download" @click="handleDownloadLog(row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="task-history__pagination">
        <el-pagination
          v-model:current-page="detailPage"
          :total="detailTotal"
          :page-size="PAGE_SIZE"
          layout="total, prev, pager, next"
          @current-change="handleDetailPageChange"
        />
      </div>
    </el-card>

    <!-- 执行日志查看（保留抽屉，长文本展示更合适） -->
    <el-drawer v-model="logVisible" :title="`执行日志 #${logExecution?.id ?? ''}`" size="640px" destroy-on-close>
      <div v-loading="logLoading" class="task-history__log">
        <pre v-if="logs.length" class="task-history__log-pre">{{ logs.map(l => `[${formatDateTime(l.created_time)}] [${l.log_level.toUpperCase()}] ${l.content}`).join('\n') }}</pre>
        <el-empty v-else description="暂无日志" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.task-history {
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
    gap: 12px;
  }

  &__back {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }

  &__server-filter {
    width: 200px;
  }

  &__table {
    flex: 1;
    min-height: 0;
  }

  &__pagination {
    display: flex;
    justify-content: flex-end;
    padding-top: 12px;
  }

  &__log {
    flex: 1;
    min-height: 0;
    overflow: auto;
    background: var(--el-fill-color-light);
    border-radius: 4px;
    padding: 12px;
  }

  &__log-pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.6;
  }
}
</style>
