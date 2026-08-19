/** WebSocket 封装：连接/断开执行实时日志流（本地部署，无鉴权）。 */

import type { WsFrame } from '@/types/openlist'

export type WsHandler = (frame: WsFrame) => void

export interface WsOptions {
  onMessage: WsHandler
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
}

export type WsState = 'connecting' | 'connected' | 'disconnected'

export function buildWsUrl(executionId: number): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.VITE_API_BASE_URL ?? '/api'
  return `${proto}://${location.host}${base}/openlist/ws/${executionId}`
}

export function connectWs(executionId: number, options: WsOptions): WebSocket {
  const ws = new WebSocket(buildWsUrl(executionId))
  ws.onopen = () => options.onOpen?.()
  ws.onmessage = event => {
    try {
      const frame = JSON.parse(event.data as string) as WsFrame
      options.onMessage(frame)
    } catch {
      /* 忽略无法解析的帧 */
    }
  }
  ws.onclose = () => options.onClose?.()
  ws.onerror = () => options.onError?.()
  return ws
}

export function disconnectWs(ws: WebSocket | null): void {
  if (ws) {
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    ws.close()
  }
}

export function wsState(ws: WebSocket | null): WsState {
  if (!ws) return 'disconnected'
  if (ws.readyState === WebSocket.OPEN) return 'connected'
  if (ws.readyState === WebSocket.CONNECTING) return 'connecting'
  return 'disconnected'
}
