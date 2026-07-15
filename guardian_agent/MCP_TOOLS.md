# Guardian Care MCP 工具说明

这层 MCP 是给涂鸦开发者平台调用的工具入口。当前仍使用本地 SQLite 和模拟数据，后续接真实服务器时，只需要把工具内部的数据来源替换掉，工具名和返回结构可以继续保留。

## 启动

```powershell
python -m pip install -r requirements.txt
python mcp_server.py
```

正式接入时建议设置密钥：

```powershell
$env:GUARDIAN_MCP_API_KEY="替换成你的密钥"
python mcp_server.py
```

## 涂鸦平台工具清单

为适配涂鸦平台工具数量上限，MCP 对外只暴露场景级工具：

- `list_elders`：返回老人列表和 `elder_id`。
- `night_care_workflow`：起夜/离床场景工作流。
- `health_report_workflow`：健康日报、周报和最近体征工作流。

原来的细粒度函数仍保留在 `guardian_tools.py` 里，方便本地测试和后续后端复用，但不再作为独立 MCP 工具暴露给涂鸦。

## night_care_workflow

通过 `action` 参数选择起夜场景里的具体步骤：

```text
list_elders
get_active_event
get_event_detail
get_event_timeline
submit_feedback
handle_elder_reply
night_turn
request_emergency_help
confirm_return_to_bed
no_response_timeout
record_device_action
close_event
```

推荐涂鸦智能体优先使用：

- `get_active_event`：查询当前待处理事件。
- `handle_elder_reply`：自动查找当前事件并写入老人反馈，适合“我没事 / 我去洗手间 / 我头晕 / 我需要帮助”等话术。
- `night_turn`：直接提交老人原话，由本地会话适配层识别意图并更新事件。
- `request_emergency_help`：老人明确求助时升级事件。
- `confirm_return_to_bed`：设备或老人端确认已返床时关闭观察事件。
- `no_response_timeout`：老人无响应超时时升级事件。
- `close_event`：确认安全后关闭归档事件。

老人说“我去洗手间”的参数示例：

```json
{
  "action": "night_turn",
  "elder_id": "E001",
  "original_text": "我去一下洗手间"
}
```

## health_report_workflow

通过 `action` 参数选择健康报告里的具体步骤：

```text
daily_report
weekly_report
get_daily_report
generate_daily_report
get_weekly_report
generate_weekly_report
get_recent_vitals
refresh_all_reports
```

推荐涂鸦智能体优先使用：

- `daily_report`：获取健康日报，缺失时自动生成。
- `weekly_report`：获取健康周报，缺失时自动生成。
- `refresh_all_reports`：重新生成日报、周报，并返回最近体征。

查询周报的参数示例：

```json
{
  "action": "weekly_report",
  "elder_id": "E001"
}
```

健康报告只用于日常照护参考，不能替代医生诊断；如果老人出现明显不适，需要及时联系医护人员。
