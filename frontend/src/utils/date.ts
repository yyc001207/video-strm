/** 日期时间格式化工具。 */

import dayjs from 'dayjs'

/** 统一时间展示格式，去除 ISO 字符串中的 T。 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}
