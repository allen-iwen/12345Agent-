import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtTime(iso: string): string {
  if (!iso) return ''
  return iso.slice(5, 16).replace('T', ' ')
}

export const STATUS_META: Record<string, { label: string; cls: string }> = {
  processing: { label: '生成中', cls: 'bg-info-subtle text-info' },
  awaiting_review: { label: '待审核', cls: 'bg-warning-subtle text-warning' },
  needs_clarification: { label: '待补充', cls: 'bg-info-subtle text-info' },
  completed: { label: '已完成', cls: 'bg-success-subtle text-success' },
  failed: { label: '失败', cls: 'bg-danger-subtle text-danger' },
}

export const NODE_META: Record<string, { label: string; short: string }> = {
  understand: { label: '诉求理解', short: '理解' },
  work_order: { label: '标准化工单', short: '工单' },
  classify: { label: '事项分类', short: '分类' },
  route: { label: '承办单位', short: '转派' },
  reply: { label: '答复草拟', short: '答复' },
}
