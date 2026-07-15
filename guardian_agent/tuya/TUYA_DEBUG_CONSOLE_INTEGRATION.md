# 涂鸦 Agent 与起夜调试台联调

## 1. 联调边界

涂鸦当前开放接口只支持查询对话记录，没有提供从自有网页提交一轮文本并同步取得 Agent 回复的接口。因此调试阶段使用两个页面：

```text
Guardian 调试台：触发硬件信号、显示事件、计时和状态机
涂鸦在线调试：输入老人自然语言、运行 LLM 和调用 Guardian MCP
```

两个服务部署在同一台服务器并使用同一个 `/opt/guardian-agent/guardian_agent.sqlite3`。`conversation.py` 只保留为本地规则兜底，服务器调试台设置为 `tuya_agent` 模式后不会调用它。

## 2. 数据流

```text
调试台触发 LEAVE_BED
  -> server.py 写入服务器 SQLite 并生成 event_id
  -> 涂鸦在线调试输入老人回答
  -> 涂鸦 Agent 调用 night_care_workflow(handle_elder_reply)
  -> Guardian MCP 更新同一个事件
  -> Guardian MCP 写入 provider=tuya_agent 的 conversation_turns
  -> 调试台每 1.5 秒刷新并展示意图、置信度、状态和建议回复
```

## 3. 服务器安装调试服务

部署新版代码后执行：

```bash
cp /opt/guardian-agent/deploy/guardian-debug.service /etc/systemd/system/guardian-debug.service
systemctl daemon-reload
systemctl enable --now guardian-debug.service
systemctl status guardian-debug.service --no-pager
```

调试服务只监听服务器 `127.0.0.1:8765`，不会直接暴露到互联网。

## 4. 从电脑打开调试台

在 Windows PowerShell 或 MobaXterm 本地终端建立 SSH 端口转发：

```powershell
ssh -L 8765:127.0.0.1:8765 root@121.43.247.31
```

保持该终端窗口打开，然后访问：

```text
http://127.0.0.1:8765
```

页面第二步应显示“涂鸦 Agent”，按钮文字应为“复制回答，前往涂鸦在线调试”。

## 5. 一次完整测试

1. 在 Guardian 调试台点击“睡眠带：离床”。
2. 确认页面生成 `event_id`，状态为 `WAITING_ELDER_CONFIRM`。
3. 在回答框选择或输入老人原话，点击复制按钮。复制内容同时包含当前 `event_id` 和老人原话。
4. 切换到涂鸦在线调试，粘贴并发送。Agent 必须把明确的 `event_id` 传给 MCP，并只把“老人原话”写入 `original_text`。
5. 确认涂鸦日志出现一次 `night_care_workflow(handle_elder_reply)`。
6. 回到 Guardian 调试台，等待不超过 2 秒。
7. “Agent 判断”区域应出现 `provider=tuya_agent`、意图、置信度和事件状态。
8. 继续在 Guardian 调试台触发返床、超时或跌倒信号。

## 6. 模式说明

服务器 systemd 服务固定使用：

```text
GUARDIAN_CONVERSATION_PROVIDER=tuya_agent
```

本机直接运行 `python server.py` 时默认使用：

```text
local_rules
```

如需在本机验证涂鸦模式，可以先设置：

```powershell
$env:GUARDIAN_CONVERSATION_PROVIDER="tuya_agent"
python server.py
```

## 7. 故障判断

- 页面显示“本地规则兜底”：`guardian-debug.service` 没有加载新版服务文件或环境变量。
- 涂鸦调用成功但页面无变化：调试台和 MCP 没有使用同一个项目目录或 SQLite。
- 页面状态变化但没有 Agent 判断卡片：服务器仍是旧版 `guardian_tools.py`，尚未写入 `conversation_turns`。
- 点击复制后无法写入剪贴板：手动复制文本框内容，不影响 Agent 和状态机流程。
