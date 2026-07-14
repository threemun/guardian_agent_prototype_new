# Guardian Edge Agent 本地原型交付说明

## 本次更新

- 修复演示控制台按钮触发后，Agent 决策时间线不随新事件变化的问题。
- 点击风险卡片后，事件详情、时间线、健康日报、健康周报、体征数据和回忆库会切换到对应老人。
- “触发健康异常”现在会同时生成健康异常事件和日报，因此能在时间线里看到 Agent 分析步骤。
- 家庭回忆标题改为 10 字以内的事件标题，不再带分类，不再简单截取录音文本。
- 回忆正文改为基于原文的故事性整理，不使用抒情模板，不虚构扩写。
- 回忆改为“一段录音生成一条完整回忆事件”，不再把同一段录音切成多个片段。
- 每条回忆的 `source_text` 保留完整原始对话转写，用于追溯完整通话逻辑。
- 回忆检索支持关键词、人物、情感、主题、回忆发生时间、录音记录时间。
- 每条回忆和录音列表都提供原录音播放控件，接口为 `GET /api/v1/recordings/{recording_id}/audio`，并支持浏览器音频播放所需的 Range 请求。
- 最近日常数据记录已增加老人姓名列，能区分三位老人。
- 新增 MCP 工具层：事件查询、老人反馈、设备动作记录、健康日报、健康周报、最近体征数据都可以由涂鸦智能体通过工具调用。
- 健康日报/周报工具已保留“获取最近报告”和“重新生成报告”两类入口，方便后续区分只读查询和主动分析。

## 启动方式

```powershell
cd "C:\Users\Wu Ting\Documents\Codex\2026-07-08\app-app\work\guardian_agent"
python server.py
```

打开：

```text
http://127.0.0.1:8765
```

## MCP 工具启动

首次运行前安装依赖：

```powershell
cd "C:\Users\Wu Ting\Documents\Codex\2026-07-08\app-app\work\guardian_agent"
python -m pip install -r requirements.txt
```

本机测试启动：

```powershell
python mcp_server.py
```

对外接入涂鸦时建议设置密钥：

```powershell
$env:GUARDIAN_MCP_API_KEY="替换成你的密钥"
$env:GUARDIAN_MCP_HOST="127.0.0.1"
$env:GUARDIAN_MCP_PORT="8000"
python mcp_server.py
```

如果涂鸦平台只能配置 URL 鉴权，可以使用：

```text
http://公网地址/mcp?key=替换成你的密钥
```

## MCP 工具清单

```text
list_elders                查看老人列表和 elder_id
get_active_event           获取某位老人最新未关闭事件
get_event_detail           获取事件详情和完整时间线
get_event_timeline         只获取事件决策时间线
submit_elder_feedback      写入老人反馈，保留原话和来源
request_emergency_help     老人请求帮助时升级事件
record_device_action       写入涂鸦设备/场景动作执行结果
close_event                关闭并归档事件
get_daily_report           获取最近健康日报
generate_daily_report      重新生成健康日报
get_weekly_report          获取最近健康周报
generate_weekly_report     重新生成健康周报
get_recent_vitals          获取最近体温、心率、血压、血糖、睡眠等数据
```

健康报告只用于日常照护参考，不能替代医生诊断。

## 主要接口

```text
GET  /api/v1/dashboard?elder_id=E001&selected_event_id=
GET  /api/v1/events
GET  /api/v1/events/{event_id}
GET  /api/v1/events/{event_id}/timeline
GET  /api/v1/reports/daily?elder_id=E001
GET  /api/v1/reports/weekly?elder_id=E001
GET  /api/v1/vitals?elder_id=E001
GET  /api/v1/memories?elder_id=&query=&person=&emotion=&topic=&memory_start_date=&memory_end_date=&recorded_start_date=&recorded_end_date=
GET  /api/v1/memories/recordings?elder_id=E001
GET  /api/v1/memories/facets?elder_id=E001
GET  /api/v1/recordings/{recording_id}/audio
POST /api/v1/messages
```

## 通话录音消息示例

```json
{
  "message_type": "call_recording",
  "message_id": "msg_call_001",
  "elder_id": "E001",
  "family_member": "王女士",
  "call_started_at": "2026-07-11T20:10:00+08:00",
  "memory_date": "1999-09-01",
  "audio_uri": "samples/audio/mom_daughter_kindergarten.wav",
  "audio_duration_seconds": 96
}
```

如果服务器已经完成转写，可以直接传 `transcript`，Agent 会跳过语音转文字，直接做回忆提取。

## 语音转文字适配

当前默认使用 `mock` 转写器，保证本地离线可跑。后续可接 FunASR / OpenAI-compatible ASR：

```powershell
$env:STT_PROVIDER="funasr"
$env:STT_BASE_URL="http://127.0.0.1:8000/v1/audio/transcriptions"
$env:STT_MODEL="sensevoice"
python server.py
```

适配位置：

```text
work/guardian_agent/agent/memory.py
```
