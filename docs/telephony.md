# 运营商 / 呼叫中心对接指南

本系统面向真实政务热线部署：通话音频经呼叫平台到达后，自动完成
**转写 → 降噪整理 → 五节点链路建单**，坐席在 Web 工作台直接进入人机协同审核。
浏览器端无需任何改造。

## 接入方式

### 方式 A：HTTP 回调（推荐，主流运营商/呼叫平台均支持）

运营商平台在通话挂机、录音生成后，向本系统推送事件：

```bash
curl -X POST http://<本机>:8000/api/telephony/webhook/call-event \
  -H "Content-Type: application/json" \
  -H "X-Telephony-Secret: <与 .env TELEPHONY_WEBHOOK_SECRET 一致>" \
  -d '{
    "call_id": "20260715093001-025",
    "event": "hangup",
    "provider": "cmcc-voip",
    "caller": "138****6677",
    "recording_url": "https://operator.example.com/rec/025.mp3"
  }'
```

- `recording_url` 支持 **http(s)**（系统自动下载）或**共享盘路径**（如
  `file:///D:/callshare/025.mp3`、`D:/callshare/025.mp3`——政府内网常用共享存储，免公网暴露）
- 回调立即返回 200，转写建单在后台异步执行（约 1–2 分钟）
- 鉴权：`X-Telephony-Secret` 头与 `.env` 的 `TELEPHONY_WEBHOOK_SECRET` 比对；
  未配置 secret 时放行并记录告警（仅限联调）
- 处理状态查询：`GET /api/telephony/calls/{call_id}`（received → processing → done/failed，
  done 时返回 `case_id`）
- 对接配置自检：`GET /api/telephony/status`

### 方式 B：录音目录投递（无回调能力时的约定式对接）

呼叫平台把录音投放到约定目录（默认 `backend/storage/telephony_recordings/`，
可通过 `.env` 的 `TELEPHONY_RECORDING_DIR` 修改），运行守护脚本：

```bash
python scripts/telephony_watcher.py          # 常驻，10s 轮询
python scripts/telephony_watcher.py --once   # 单次扫描（联调/演示）
```

文件名即 `call_id`；处理完成自动移入 `processed/` 归档。

### 方式 C：SIP 中继（规划位）

政府侧已有 PBX（Asterisk/FreeSWITCH）时，经 SIP 中继 + ESL 事件对接，
音频流（RTP）转 PCM 后走同一条转写建单链路。配置字段已预留
（`TELEPHONY_PROVIDER=sip`），媒体网关侧部署时实施。

## 配置项（backend/.env）

| 变量 | 默认 | 说明 |
|---|---|---|
| `TELEPHONY_PROVIDER` | `generic` | `generic`=回调/目录；`sip`=FreeSWITCH 规划位 |
| `TELEPHONY_WEBHOOK_SECRET` | 空 | 回调鉴权密钥，**生产必配**；空=放行并告警 |
| `TELEPHONY_RECORDING_DIR` | `storage/telephony_recordings` | 方式 B 的投递目录 |

## 建单行为

- 案件号：`tel-{call_id}`；来电源：`电话（运营商接入）`
- 转写走与人工上传**完全相同**的双引擎链路（讯飞云端 → 本地兜底 → LLM 降噪整理），
  原始转写全文留存作证据
- 建单后案件状态为 `awaiting_review`，坐席在 Web 工作台审核——
  **智能体不直接对派单结果负责，人工放行才归档**（政务合规要求）
- 每通电话的事件与处理状态持久化在 SQLite `call_events` 表，可审计可重放

## 联调自检清单

1. `GET /api/telephony/status` → provider/secret/目录三项就绪
2. 用本地录音模拟回调（`recording_url` 直接填本机路径）：
   ```bash
   curl -X POST http://127.0.0.1:8000/api/telephony/webhook/call-event \
     -H "Content-Type: application/json" \
     -d '{"call_id":"test-001","event":"hangup","recording_url":"D:/workspace/12345工单热线/12345agent/backend/data/raw/official_work_orders/交通运输/260715111208005.mp3"}'
   ```
3. 轮询 `GET /api/telephony/calls/test-001` 直至 `status=done`，拿 `case_id` 到工作台查看
