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

## 事件工具

- `list_elders`：返回老人列表和 `elder_id`。
- `get_active_event`：返回某位老人最新未关闭照护事件。
- `get_event_detail`：返回事件详情、风险等级、老人信息和完整时间线。
- `get_event_timeline`：只返回事件的观察、判断、工具调用、反馈记录。
- `submit_elder_feedback`：写入老人反馈，支持 `ok`、`bathroom`、`drink`、`dizzy`、`need_help`，并保存老人原话。
- `request_emergency_help`：老人明确求助时升级事件。
- `record_device_action`：记录涂鸦设备或场景动作是否执行成功。
- `close_event`：确认安全后关闭归档事件。

## 健康报告工具

- `get_daily_report`：获取某位老人最近一次健康日报。
- `generate_daily_report`：根据最近体征重新生成健康日报。
- `get_weekly_report`：获取某位老人最近一次健康周报。
- `generate_weekly_report`：根据最近一周体征重新生成健康周报。
- `get_recent_vitals`：获取最近体温、心率、血压、血糖、血氧、睡眠和步数记录。

健康报告只用于日常照护参考，不能替代医生诊断；如果老人出现明显不适，需要及时联系医护人员。
