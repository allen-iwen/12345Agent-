// 轻量全局状态：当前选中案件 + 轨迹抽屉
import { create } from 'zustand'

interface AppState {
  selectedCaseId: string | null
  traceNode: string | null // 打开轨迹抽屉的节点名
  select: (id: string | null) => void
  openTrace: (node: string) => void
  closeTrace: () => void
}

export const useApp = create<AppState>((set) => ({
  selectedCaseId: null,
  traceNode: null,
  select: (id) => set({ selectedCaseId: id, traceNode: null }),
  openTrace: (node) => set({ traceNode: node }),
  closeTrace: () => set({ traceNode: null }),
}))
