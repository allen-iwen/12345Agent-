// 相似工单参考面板：BM25 检索官方历史工单，坐席员可一键参考/复用其办理口径
import useSWR from 'swr'
import { BookOpen, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { Badge, Card, CardBody, CardHeader, CardTitle, Spinner } from '../ui'

export function SimilarPanel({ rawText }: { rawText: string }) {
  const { data, isLoading } = useSWR(
    rawText ? ['similar', rawText] : null,
    () => api.searchSimilar(rawText, 3),
  )
  const [copied, setCopied] = useState<string | null>(null)

  const copy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(id)
      setTimeout(() => setCopied(null), 1600)
    } catch {
      /* clipboard 不可用时忽略 */
    }
  }

  return (
    <Card>
      <CardHeader>
        <BookOpen className="h-4 w-4 text-primary" />
        <CardTitle>相似官方工单 · 一键参考</CardTitle>
        <span className="text-[11px] text-muted ml-auto">BM25 检索 18 条官方样例</span>
      </CardHeader>
      <CardBody className="space-y-3">
        {isLoading && (
          <div className="flex items-center gap-2 text-muted text-sm py-4">
            <Spinner /> 检索中…
          </div>
        )}
        {!isLoading && (!data || data.hits.length === 0) && (
          <div className="text-sm text-muted py-4">未检索到相似工单</div>
        )}
        {data?.hits.map((h) => (
          <div key={h.source_id} className="border border-border rounded-md p-3 hover:border-primary/50 transition-colors group">
            <div className="flex items-start gap-2">
              <Badge tone="primary">{h.category}</Badge>
              <span className="text-sm font-medium leading-snug flex-1">{h.title}</span>
              <span className="text-[10px] font-mono text-muted-light shrink-0 pt-1">{h.score.toFixed(1)}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {h.handling_departments.map((d) => (
                <span key={d} className="text-[11px] bg-surface-hover text-text-secondary rounded px-1.5 py-0.5">
                  {d}
                </span>
              ))}
            </div>
            {h.reply_content && (
              <div className="mt-2 relative">
                <p className="text-xs text-muted leading-relaxed line-clamp-3 pr-7">{h.reply_content}</p>
                <button
                  onClick={() => copy(h.source_id, h.reply_content)}
                  className="absolute right-0 top-0 p-1 rounded text-muted-light hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity"
                  title="复制官方答复全文"
                >
                  {copied === h.source_id ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
              </div>
            )}
          </div>
        ))}
      </CardBody>
    </Card>
  )
}
