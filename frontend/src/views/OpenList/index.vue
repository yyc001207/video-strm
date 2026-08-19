<script setup lang="ts">
import { nextTick, ref } from 'vue'

import GlobalConfig from './components/GlobalConfig.vue'
import PresetManage from './components/PresetManage.vue'
import TaskManage from './components/TaskManage.vue'
import Execution from './components/Execution.vue'
import TaskHistory from './components/TaskHistory.vue'
import RealtimeLog from './components/RealtimeLog.vue'

const activeTab = ref('config')

const configRef = ref<InstanceType<typeof GlobalConfig> | null>(null)
const presetRef = ref<InstanceType<typeof PresetManage> | null>(null)
const taskRef = ref<InstanceType<typeof TaskManage> | null>(null)
const executionRef = ref<InstanceType<typeof Execution> | null>(null)
const historyRef = ref<InstanceType<typeof TaskHistory> | null>(null)
const realtimeRef = ref<InstanceType<typeof RealtimeLog> | null>(null)

/**
 * 标签页切换（仅从非当前标签点击触发；点当前激活标签不触发 tab-change）：
 * 激活哪个标签就立即刷新哪个标签的接口数据，实现按需动态加载。
 */
function handleTabChange(name: string) {
  const reloads: Record<string, (() => void) | undefined> = {
    config: configRef.value?.reload,
    preset: presetRef.value?.reload,
    task: taskRef.value?.reload,
    execution: executionRef.value?.reload,
    history: historyRef.value?.reload,
    realtime: realtimeRef.value?.reload
  }
  reloads[name]?.()
}

/**
 * 从执行管理页触发：切到实时日志页，让该页先连接日志、连接成功后再启动执行。
 * 支持多任务批量执行：executionIds 数组 + 对应 taskIds/taskNames，默认展示第一个，可切换。
 */
function handleNavigate(tab: string, payload?: Record<string, unknown>) {
  activeTab.value = tab
  if (tab === 'realtime' && payload?.executionIds) {
    const ids = payload.executionIds as number[]
    const taskIds = (payload.taskIds as number[]) ?? []
    const taskNames = (payload.taskNames as string[]) ?? []
    const serverId = payload.serverId as number | undefined
    nextTick(() => {
      realtimeRef.value?.setExecutions(
        ids.map((id, idx) => ({
          executionId: id,
          taskId: taskIds[idx] ?? 0,
          taskName: taskNames[idx] ?? `执行 #${id}`
        })),
        serverId
      )
    })
  }
}
</script>

<template>
  <div class="openlist">
    <el-tabs v-model="activeTab" class="openlist__tabs" @tab-change="handleTabChange">
      <el-tab-pane label="全局配置" name="config" lazy>
        <GlobalConfig ref="configRef" />
      </el-tab-pane>
      <el-tab-pane label="预设配置" name="preset" lazy>
        <PresetManage ref="presetRef" />
      </el-tab-pane>
      <el-tab-pane label="任务配置" name="task" lazy>
        <TaskManage ref="taskRef" />
      </el-tab-pane>
      <el-tab-pane label="执行管理" name="execution" lazy>
        <Execution ref="executionRef" @navigate="handleNavigate" />
      </el-tab-pane>
      <el-tab-pane label="任务历史" name="history" lazy>
        <TaskHistory ref="historyRef" />
      </el-tab-pane>
      <el-tab-pane label="实时日志" name="realtime" lazy>
        <RealtimeLog ref="realtimeRef" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped lang="scss">
.openlist {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;

  &__tabs {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;

    :deep(.el-tabs__content) {
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    :deep(.el-tab-pane) {
      height: 100%;
      overflow: hidden;
    }
  }
}
</style>
