/** OpenList 任务调度接口封装。 */

import axios from 'axios'
import { ElMessage } from 'element-plus'

import request from './index'
import type {
  BatchDirExecutionParams,
  ExecutionStatus,
  HistorySummaryItem,
  OpenListConfig,
  OpenListExecution,
  OpenListLog,
  OpenListServer,
  OpenListServerCreate,
  OpenListServerUpdate,
  OpenListTask,
  Res,
  ServerDirItem
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
  /** 快速追加父级目录（仅校验新增部分，不动已有目录）。 */
  addServerParentDirs(serverId: number, parentDirs: string[], skipValidation = false): Promise<Res<OpenListServer>> {
    return request.post(`/openlist/servers/${serverId}/parent-dirs`, {
      parent_dirs: parentDirs,
      skip_validation: skipValidation
    })
  },
  /** 查询服务器某路径下一级子目录（缓存优先）。 */
  getServerDirs(serverId: number, path?: string): Promise<Res<{ path: string; list: ServerDirItem[] }>> {
    return request.get(`/openlist/servers/${serverId}/dirs`, { params: path ? { path } : {} })
  },
  /** 按关键字逐层搜索目录（缓存优先；放宽超时，深层目录搜索耗时较长）。 */
  searchServerDirs(serverId: number, keyword: string, path?: string): Promise<Res<{ path: string; list: ServerDirItem[] }>> {
    return request.get(`/openlist/servers/${serverId}/dirs/search`, {
      params: { keyword, ...(path ? { path } : {}) },
      timeout: 90000
    })
  },
  /** 手动刷新服务器某路径下一级子目录缓存。 */
  refreshServerDirs(serverId: number, path?: string): Promise<Res<{ path: string; list: ServerDirItem[]; count: number }>> {
    return request.post(`/openlist/servers/${serverId}/dirs/refresh`, { path: path || undefined })
  },

  /** 任务列表（含最近一次执行，可按服务器筛选）。 */
  listTasks(keyword?: string, serverId?: number | null): Promise<Res<{ list: OpenListTask[] }>> {
    return request.get('/openlist/tasks', {
      params: {
        ...(keyword ? { keyword } : {}),
        ...(serverId ? { server_id: serverId } : {})
      }
    })
  },
  getTask(id: number): Promise<Res<OpenListTask>> {
    return request.get(`/openlist/tasks/${id}`)
  },
  createTask(data: { server_id: number; name: string; output_dir: string; process_path: string; pause_count?: number; pause_time?: string }): Promise<Res<OpenListTask>> {
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
  /** 批量创建目录执行记录（同一服务器多目录，不关联任务，仅落库）。 */
  batchCreateDirExecutions(params: BatchDirExecutionParams): Promise<Res<{ list: OpenListExecution[] }>> {
    return request.post('/openlist/executions/dirs', params)
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

  /** 任务历史：每个任务最近一次执行（可按服务器筛选）。 */
  historySummary(serverId?: number | null): Promise<Res<{ list: HistorySummaryItem[] }>> {
    return request.get('/openlist/history', { params: serverId ? { server_id: serverId } : {} })
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
