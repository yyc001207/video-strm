/** OpenList 状态：全局配置、服务器、预设、任务、执行与实时日志连接。 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  openlistApi,
  type BatchExecutionParams,
  type ExecutionLaunchParams,
  type ExecutionStartParams
} from '@/api/openlist'
import type {
  OpenListConfig,
  OpenListExecution,
  OpenListPreset,
  OpenListServer,
  OpenListTask
} from '@/types/openlist'

export const useOpenlistStore = defineStore('openlist', () => {
  const config = ref<OpenListConfig | null>(null)
  const servers = ref<OpenListServer[]>([])
  const presets = ref<OpenListPreset[]>([])
  const tasks = ref<OpenListTask[]>([])
  const runningExecutions = ref<OpenListExecution[]>([])
  const activeExecutionIds = ref<number[]>([])

  const runningTaskIds = computed(() => new Set(runningExecutions.value.map(e => e.task_id)))

  async function fetchConfig(): Promise<void> {
    const res = await openlistApi.getConfig()
    config.value = res.data
    servers.value = res.data.servers ?? []
  }

  async function fetchPresets(): Promise<void> {
    const res = await openlistApi.listPresets()
    presets.value = res.data.list
  }

  async function fetchTasks(): Promise<void> {
    const res = await openlistApi.listTasks()
    tasks.value = res.data.list
  }

  async function fetchRunning(): Promise<void> {
    const res = await openlistApi.listExecutions({ status: 'running', page: 1, pageSize: 50 })
    runningExecutions.value = res.data.list
  }

  /** 创建执行记录（仅落库，返回 execution_id 供前端先连日志）。 */
  async function createExecution(params: ExecutionStartParams): Promise<OpenListExecution> {
    const res = await openlistApi.createExecution(params)
    activeExecutionIds.value = [res.data.id]
    return res.data
  }

  /** 批量创建执行记录（同一服务器多任务，仅落库），返回全部 execution。 */
  async function batchCreateExecution(serverId: number, tasksToRun: BatchExecutionParams['tasks']): Promise<OpenListExecution[]> {
    const res = await openlistApi.batchCreateExecutions({ server_id: serverId, tasks: tasksToRun })
    activeExecutionIds.value = res.data.list.map(e => e.id)
    return res.data.list
  }

  /** 启动已创建的执行记录（日志连接成功后再调用）。 */
  async function startExecution(params: ExecutionLaunchParams): Promise<OpenListExecution> {
    const res = await openlistApi.startExecution(params)
    await fetchRunning()
    return res.data
  }

  async function cancelExecution(executionId: number): Promise<void> {
    await openlistApi.cancelExecution(executionId)
    await fetchRunning()
  }

  return {
    config,
    servers,
    presets,
    tasks,
    runningExecutions,
    activeExecutionIds,
    runningTaskIds,
    fetchConfig,
    fetchPresets,
    fetchTasks,
    fetchRunning,
    createExecution,
    batchCreateExecution,
    startExecution,
    cancelExecution
  }
})
