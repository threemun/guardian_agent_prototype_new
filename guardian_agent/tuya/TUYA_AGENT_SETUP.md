# Guardian Care Agent 涂鸦搭建与触发说明

## 1. 当前架构

```text
涂鸦 Agent = LLM + 系统 Prompt + 会话上下文 + MCP 工具选择
Guardian MCP = 3 个场景级工具入口
Guardian 服务 = 状态机 + 安全规则 + 报告计算 + SQLite（当前）
```

涂鸦 Agent 替代的是本地 `Conversation` 的意图理解职责，不替代 Guardian 状态机。

## 2. 为什么必须更新公网 MCP

涂鸦平台只能访问公网 HTTPS MCP，不能访问电脑上的 `127.0.0.1`。当前涂鸦配置指向公网服务器 `/opt/guardian-agent`，因此本地代码改动不会自动生效。

本地 MCP 变化后需要：

1. 运行本地测试。
2. 将新版代码发布到服务器 `/opt/guardian-agent`。
3. 只重启 `guardian-mcp.service`。
4. 不重启 `guardian-mcp-tunnel.service`，否则临时公网 URL 可能变化。
5. 运行 `tests/mcp_smoke.py`，应发现三个工具。
6. 在涂鸦 MCP 服务详情页刷新工具列表。

如果公网 URL、访问密钥和数据中心没有变化，不需要重新创建 MCP 配置。

## 3. 在涂鸦平台创建 Agent

1. 进入 `AI 智能体 > 智能体开发 > 我的智能体`。
2. 创建 Agent：
   - 名称：`Guardian Care Agent`
   - 角色：独居老人居家照护助手
   - 数据中心：必须与 Guardian MCP 注册的数据中心一致
3. 选择中文表现稳定的模型。
4. 会话记忆消息数先设为 6，避免上下文过长。
5. 在变量区域新增：
   - 名称：`custom_guardianElderId`
   - 描述：当前会话绑定的 Guardian 老人 ID
   - 调试默认值：`E001`
6. 在技能配置的工具集中添加自定义 `Guardian Care MCP`。
7. 确认只看到并添加：
   - `list_elders`
   - `night_care_workflow`
   - `health_report_workflow`
8. 将 `tuya/GUARDIAN_CARE_AGENT_PROMPT.md` 的正文粘贴到系统 Prompt。
9. 保存开发版本。

## 4. 第一次在线调试

### MCP 工具页先验收

1. 试运行 `list_elders`，参数 `{}`。
2. 试运行 `night_care_workflow`：

```json
{
  "action": "simulate_guardian_scenario",
  "elder_id": "E001",
  "scenario_code": "normal_bathroom",
  "confidence": ""
}
```

`confidence` 是字符串字段。当前动作不使用置信度，因此可以保留空字符串 `""`；处理老人回答时传入 `"0.91"` 这样的字符串，Guardian 服务会在进入状态机前转换成浮点数。

3. 再试运行：

```json
{
  "action": "get_active_event",
  "elder_id": "E001"
}
```

应得到真实 `event_id` 和 `WAITING_ELDER_CONFIRM`。

### Agent 在线对话测试

在 Agent 编排页选择“在线调试”，依次输入：

1. `我去趟卫生间，不用担心。`
   - 期望：直接调用一次 `night_care_workflow(action=handle_elder_reply, feedback_type=bathroom)`；`event_id` 留空，由服务端自动查找活动事件。
   - 期望状态：`MONITORING_RETURN`。
   - 最终回复应类似：“好的，您慢点走，注意脚下，我会留意您是否安全返床。”
   - 回复中不得出现思考过程、工具名、action、参数或重复计划。
2. 重新创建 `dizzy` 场景后输入：`我没事，就是站起来有点晕。`
   - 期望意图：`dizzy`，不能被“没事”覆盖。
   - 期望状态：`WAITING_FAMILY_CONFIRM`。
3. `帮我看一下今天的健康日报。`
   - 期望：`health_report_workflow(action=daily_report)`。
4. `最近一周有什么变化？`
   - 期望：`health_report_workflow(action=weekly_report)`。

在调试详情中检查每一轮的模型节点、工具名、工具参数和工具返回。

更新系统 Prompt 后必须新建或清空在线调试会话，避免旧会话记忆继续携带此前的错误工具调用。若模型只输出“准备调用工具”却没有工具节点，检查该 Agent 开发版本是否已经绑定并启用 `Guardian Care MCP`，以及当前模型是否支持工具调用。

## 5. Agent 如何被触发

### 开发阶段

在涂鸦 Agent 编排页的“在线调试”输入文字。发送一轮文字就会触发一次 Agent 运行，Agent 决定是否调用 MCP。

### 涂鸦 App / 智能生活 App

在“应用管理”选择 App 载体并保存，平台会生成 Agent 对话小程序。使用调试二维码或投放后的访问路径打开小程序，用户发送文字或语音即可触发 Agent。

### 涂鸦产品设备

将 Agent 投放并绑定到产品 PID。设备激活后，设备端语音对话可触发绑定的 Agent。真实硬件尚不可用时，可在在线调试中绑定虚拟设备 ID。

### 设备事件自动触发

涂鸦“智能体触发器”目前基于产品 PID 的 DP 事件。手册说明当前任务只支持提示消息，不支持直接配置插件或工作流任务。因此比赛主线暂时不要依赖它自动执行完整起夜闭环，需先做单独验证。

### 自有 hjky Web/APP

当前本地手册只提供查询历史会话等开放 API，没有确认“提交一轮文本给指定 Agent 并实时取得回复”的 OpenAPI。因此当前不能让 `hjky-web`、`hjky-app` 直接假定可 POST 调用涂鸦 Agent。

现阶段采用：

```text
电脑调试：涂鸦在线调试页 -> 涂鸦 Agent -> 公网 Guardian MCP
手机调试：涂鸦生成的 Agent 对话小程序
自有 APP：保留 AgentConversationAdapter，待确认官方会话 SDK/OpenAPI 后实现 TuyaProvider
```

## 6. 必须注意的数据边界

当前有两份独立 SQLite：

```text
本地调试网页 -> 本机 SQLite
涂鸦 Agent -> 公网服务器 SQLite
```

所以本地网页创建的事件，公网涂鸦 Agent 默认看不到。涂鸦在线调试应通过公网 MCP 的 `simulate_guardian_scenario` 创建事件。

后续接入 `hjky-server/MySQL` 后，Web、APP、MCP 和设备才会读写同一份事件数据。

## 7. 验收标准

- 涂鸦工具列表是当前三个聚合工具。
- 起夜自然语言由涂鸦 LLM 分类，不调用本地 `night_turn/Conversation`。
- Guardian 状态机仍负责状态变化和高风险护栏。
- 日报、周报均来自 `health_report_workflow` 返回数据。
- 高风险不能被 Agent 自动关闭。
- MCP 更新后公网 smoke test 通过。

## 8. 与起夜调试台联调

涂鸦 Agent 与原起夜调试台的共享数据库部署、SSH 访问方式和操作步骤见：

`tuya/TUYA_DEBUG_CONSOLE_INTEGRATION.md`
