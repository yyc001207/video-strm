/** OpenList 任务调度相关类型定义（与后端 openlist 模块字段保持一致）。 */

import type { Res } from '@/types/upload'

export interface OpenListServer {
  id: number
  name: string | null
  server_url: string
  is_active: boolean
  has_token: boolean
}

export interface OpenListServerCreate {
  name?: string
  server_url: string
  token?: string
}

export interface OpenListServerUpdate {
  name?: string
  server_url?: string
  token?: string
  is_active?: boolean
}

export interface OpenListConfig {
  id: number | null
  servers: OpenListServer[]
  video_formats: string
  subtitle_formats: string
  max_concurrent: number
  pause_count: number
  pause_time: string
  disable_ssl_verify: boolean
  log_to_db: boolean
}

export interface OpenListPreset {
  id: number
  name: string
  preset_path: string
  sort_order: number
  created_time: string | null
}

export interface OpenListTask {
  id: number
  name: string
  output_dir: string
  process_path: string
  pause_count: number | null
  pause_time: string | null
  created_time: string | null
  updated_time: string | null
  last_execution: OpenListExecution | null
}

export type ExecutionStatus = 'running' | 'success' | 'fail' | 'cancelled'

export interface OpenListExecution {
  id: number
  task_id: number
  task_name: string
  server_id: number | null
  server_name: string | null
  status: ExecutionStatus
  video_success_count: number
  video_total_count: number
  subtitle_success_count: number
  subtitle_total_count: number
  is_incremental: boolean
  is_force: boolean
  strm_only: boolean
  duration_seconds: number | null
  log_path: string | null
  started_time: string | null
  finished_time: string | null
  created_time: string | null
}

export interface OpenListLog {
  id: number
  execution_id: number
  log_level: 'info' | 'warn' | 'error' | 'progress'
  content: string
  metadata: Record<string, unknown> | null
  created_time: string | null
}

export interface HistorySummaryItem {
  task_id: number
  task_name: string
  output_dir: string
  process_path: string
  execution: OpenListExecution | null
}

/** WebSocket 实时帧（按 type 分派）。 */
export interface WsLogFrame {
  type: 'log'
  level: 'info' | 'warn' | 'error' | 'progress'
  message: string
  ts: string
}

export interface WsProgressFrame {
  type: 'progress'
  data: {
    totalVideos: number
    successVideos: number
    totalSubtitles: number
    successSubtitles: number
  }
}

export interface WsStatusFrame {
  type: 'status'
  status: ExecutionStatus
  video_success_count: number
  video_total_count: number
  subtitle_success_count: number
  subtitle_total_count: number
}

export type WsFrame = WsLogFrame | WsProgressFrame | WsStatusFrame

export type { Res }
