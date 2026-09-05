// 麦克风录音 hook：getUserMedia + MediaRecorder，停止后回调音频文件
// 用法：const { rec, recSec, start, stop } = useMicRecorder((file) => upload(file))
// 依赖安全上下文（localhost 或 HTTPS）；权限被拒/不支持时回调不会触发，由调用方提示
import { useRef, useState } from 'react'

export type MicState = 'idle' | 'recording'

export function useMicRecorder(onFile: (f: File) => void, maxSec = 299) {
  const [rec, setRec] = useState<MicState>('idle')
  const [recSec, setRecSec] = useState(0)
  const [micError, setMicError] = useState('')
  const ref = useRef<{ mr: MediaRecorder; timer: number } | null>(null)

  const stop = () => {
    const r = ref.current
    if (!r) return
    window.clearInterval(r.timer)
    ref.current = null
    setRec('idle')
    r.mr.stop() // onstop → 组装文件 → onFile
  }

  const start = async () => {
    setMicError('')
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setMicError('此页面无法调用麦克风：请用 http://127.0.0.1 访问，或部署为 HTTPS')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime =
        ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((t) => MediaRecorder.isTypeSupported(t)) || ''
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      const chunks: Blob[] = []
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const ext = mime.includes('mp4') ? 'm4a' : 'webm'
        const f = new File(chunks, `mic-${new Date().toISOString().slice(11, 19).replace(/:/g, '')}.${ext}`, {
          type: mime || 'audio/webm',
        })
        onFile(f)
      }
      mr.start(500)
      const timer = window.setInterval(() => {
        setRecSec((s) => {
          if (s >= maxSec) {
            stop()
            return 0
          }
          return s + 1
        })
      }, 1000)
      ref.current = { mr, timer }
      setRecSec(0)
      setRec('recording')
    } catch (e) {
      setMicError('麦克风不可用或权限被拒绝：' + String(e))
    }
  }

  return { rec, recSec, micError, start, stop }
}
