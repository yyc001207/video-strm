/** OpenList 任务调度接口封装。 */

import axios from 'axios'
import { ElMessage } from 'element-plus'

import request from './index'
import type {
  ExecutionStatus,
  HistorySummaryItem,
  OpenListConfig,
  OpenListExecution,
  OpenListLog,
  OpenListPreset,
  OpenListServer,
  OpenListServerCreate,
  OpenListServerUpdate,
  OpenListTask,
  Res
} from '@/types/openlist'

export interface ExecutionStartParams {
  task_id: number
  server_id: number
  is_incremental: boolean
  is_force: boolean
  strm_only: boolean
}

export interface ExecutionLaunchParams {
  execution_id: number
  task_id: number
  server_id: number
}

export interface BatchExecutionTask {
  task_id: number
  is_incremental: boolean
  is_force: boolean
  strm_only: boolean
}

export interface BatchExecutionParams {
  server_id: number
  tasks: BatchExecutionTask[]
}

export const openlistApi = {
  /** 读取全局配置（token 不返回明文）。 */
  getConfig(): Promise<Res<OpenListConfig>> {
    return request.get('/openlist/config')
  },
  /** 保存全局配置（视频/字幕格式 + 并发度）。 */
  updateConfig(data: Partial<OpenListConfig>): Promise<Res<OpenListConfig>> {
    return request.post('/openlist/config', data)
  },

  /** 服务器配置 CRUD。 */
  listServers(): Promise<Res<{ list: OpenListServer[] }>> {
    return request.get('/openlist/servers')
  },
  createServer(data: OpenListServerCreate): Promise<Res<OpenListServer>> {
    return request.post('/openlist/servers', data)
  },
  updateServer(id: number, data: OpenListServerUpdate): Promise<Res<OpenListServer>> {
    return request.post(`/openlist/servers/${id}`, data)
  },
  deleteServer(id: number): Promise<Res<null>> {
    return request.post('/openlist/servers/delete', { id })
  },

  /** 预设列表。 */
  listPresets(): Promise<Res<{ list: OpenListPreset[] }>> {
    return request.get('/openlist/presets')
  },
  createPreset(data: { name: string; preset_path: string; sort_order: number }): Promise<Res<OpenListPreset>> {
    return request.post('/openlist/presets', data)
  },
  updatePreset(id: number, data: Partial<OpenListPreset>): Promise<Res<OpenListPreset>> {
    return request.post(`/openlist/presets/${id}`, data)
  },
  deletePreset(id: number): Promise<Res<null>> {
    return request.post('/openlist/presets/delete', { id })
  },
  batchDeletePresets(ids: number[]): Promise<Res<null>> {
    return request.post('/openlist/presets/batch-delete', { ids })
  },
  reorderPresets(ids: number[]): Promise<Res<null>> {
    return request.post('/openlist/presets/reorder', { ids })
  },

  /** 任务列表（含最近一次执行）。 */
  listTasks(keyword?: string): Promise<Res<{ list: OpenListTask[] }>> {
    return request.get('/openlist/tasks', { params: keyword ? { keyword } : {} })
  },
  getTask(id: number): Promise<Res<OpenListTask>> {
    return request.get(`/openlist/tasks/${id}`)
  },
  createTask(data: { name: string; output_dir: string; process_path: string; pause_count?: number; pause_time?: string }): Promise<Res<OpenListTask>> {
    return request.post('/openlist/tasks', data)
  },
  updateTask(id: number, data: Partial<OpenListTask>): Promise<Res<OpenListTask>> {
    return request.post(`/openlist/tasks/${id}`, data)
  },
  deleteTask(id: number): Promise<Res<null>> {
    return request.post('/openlist/tasks/delete', { id })
  },
  batchDeleteTasks(ids: number[]): Promise<Res<null>> {
    return request.post('/openlist/tasks/batch-delete', { ids })
  },

  /** 启动执行。 */
  /** 创建执行记录（仅落库，不启动后台）。 */
  createExecution(params: ExecutionStartParams): Promise<Res<OpenListExecution>> {
    return request.post('/openlist/executions', params)
  },
  /** 批量创建执行记录（同一服务器多任务，仅落库）。 */
  batchCreateExecutions(params: BatchExecutionParams): Promise<Res<{ list: OpenListExecution[] }>> {
    return request.post('/openlist/executions/batch', params)
  },
  /** 启动已创建的执行记录（前端先连日志，连接成功后再启动）。 */
  startExecution(params: ExecutionLaunchParams): Promise<Res<OpenListExecution>> {
    return request.post('/openlist/executions/start', params)
  },
  cancelExecution(executionId: number): Promise<Res<{ cancelled: boolean; status: ExecutionStatus }>> {
    return request.post('/openlist/executions/cancel', { execution_id: executionId })
  },
  /** 执行记录列表（分页）。 */
  listExecutions(params: { task_id?: number; status?: ExecutionStatus; page: number; pageSize: number }): Promise<Res<{ list: OpenListExecution[] }>> {
    return request.get('/openlist/executions', { params })
  },
  getExecutionDetail(id: number): Promise<Res<{ execution: OpenListExecution; logs: OpenListLog[] }>> {
    return request.get(`/openlist/executions/${id}`)
  },

  /** 任务历史：每个任务最近一次执行。 */
  historySummary(): Promise<Res<{ list: HistorySummaryItem[] }>> {
    return request.get('/openlist/history')
  },
  /** 指定任务的全部执行记录。 */
  historyByTask(taskId: number, page: number, pageSize: number): Promise<Res<{ list: OpenListExecution[] }>> {
    return request.get(`/openlist/history/task/${taskId}`, { params: { page, pageSize } })
  },
  /** 执行日志（分页）。 */
  listExecutionLogs(executionId: number, page: number, pageSize: number): Promise<Res<{ list: OpenListLog[] }>> {
    return request.get(`/openlist/history/${executionId}/logs`, { params: { page, pageSize } })
  },
  /** 下载执行日志文件（blob，本地部署无鉴权）。 */
  async downloadLog(executionId: number): Promise<void> {
    const response = await axios.get(`/openlist/executions/${executionId}/log-download`, {
      baseURL: import.meta.env.VITE_API_BASE_URL,
      responseType: 'blob',
      timeout: 60000
    })
    const blob = response.data as Blob
    const disposition = response.headers['content-disposition'] || ''
    let filename = `execution_${executionId}.log`
    const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)/)
    if (filenameMatch?.[1]) {
      try {
        filename = decodeURIComponent(filenameMatch[1])
      } catch {
        /* 忽略解码失败，使用默认文件名 */
      }
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('日志下载成功')
  }
}
