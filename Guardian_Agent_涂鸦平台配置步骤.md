# Guardian Agent 涂鸦平台配置 README

这份文档给团队成员使用，说明如何在涂鸦平台配置“慧简 Guardian 照护助手”智能体，并把它接到我们自己的 Guardian MCP 服务上。

当前目标不是把全部养老业务逻辑写进涂鸦平台，而是让涂鸦承担“智能体入口、语音交互、设备生态、设备控制”，让我们自己的 Guardian Agent 承担“风险判断、case 管理、时间线记录、闭环归档、Web 看板展示”。

## 一、系统分工

整体关系可以理解为：

```text
老人 / 家属
  -> 涂鸦智能体
  -> Guardian MCP
  -> Guardian Agent
  -> case / timeline / feedback / close
  -> Web 看板展示
```

涂鸦平台负责：

```text
1. 提供智能体入口
2. 接收老人自然语言反馈
3. 未来控制真实涂鸦设备，例如夜灯、插座、场景
4. 承载智能生活 App 或涂鸦 App 内的体验
```

Guardian Agent 负责：

```text
1. 接收风险事件
2. 创建和更新 case
3. 记录 Agent 决策时间线
4. 根据老人反馈降级、观察、升级或关闭事件
5. 给 Web 看板提供可解释的事件过程
```

## 二、涂鸦平台入口

进入涂鸦开发者平台：

```text
https://platform.tuya.com/
```

进入智能体相关功能后，创建或维护我们的智能体：

```text
慧简 Guardian 照护助手
```

如果平台中已经有该智能体，就继续在原智能体上配置；不要重复创建多个同名智能体，避免后面调试时不知道哪个才是有效版本。

## 三、智能体角色建议

角色设定建议使用“居家照护助手”，不要写成“医生”或“医疗诊断助手”。

推荐描述：

```text
你是慧简 Guardian 居家照护助手，负责协助老人和家属处理居家照护场景中的提醒、确认和反馈。

你可以帮助确认老人当前状态，例如是否没事、是否去洗手间、是否喝水、是否头晕、是否需要帮助。

你不能做医学诊断，不能替代医生、护工、家属或急救系统。

当老人表达头晕、摔倒、疼痛、无法起身、需要帮助、呼吸不适等高风险信息时，应优先调用工具请求紧急帮助或通知家属。
```

比赛展示时也建议这样讲：我们做的是“照护风险闭环”，不是“医疗诊断”。

## 四、配置 MCP 服务

在涂鸦平台中进入：

```text
MCP 管理 -> 自定义 MCP 服务 -> 添加自定义 MCP
```

接入方式选择：

```text
Streamable HTTP
```

数据中心选择：

```text
中国数据中心
```

MCP 服务配置框中必须填 JSON。涂鸦要求外层是 `mcpServers`，不是直接填一个 URL，也不是填工具参数。

配置格式如下：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://你的公网地址/mcp?key=你的MCP访问密钥"
    }
  }
}
```

其中：

```text
guardian-care-streamableHTTP
  是这个 MCP 服务在涂鸦里的名字，可以保持不变。

url
  是 Guardian MCP 的公网 HTTPS 地址。

/mcp
  是 MCP 服务路径。

?key=xxx
  是访问 MCP 的鉴权参数。
```

## 五、为什么 URL 里带 key

常见 MCP 客户端可以通过请求头传密钥：

```text
Authorization: Bearer xxx
```

但涂鸦平台的 MCP 配置不允许写 `headers` 字段。如果写了：

```json
{
  "headers": {
    "Authorization": "Bearer xxx"
  }
}
```

涂鸦会报错：

```text
MCP配置包含禁止使用的字段: headers
```

所以我们改成了 URL query 参数：

```text
https://你的公网地址/mcp?key=你的MCP访问密钥
```

当前 MCP 服务同时支持两种鉴权方式：

```text
Authorization: Bearer <key>
?key=<key>
```

涂鸦侧使用第二种。

## 六、保存配置后如何试运行

配置保存成功后，进入 MCP 工具页面，逐个试运行工具。

推荐顺序：

```text
1. list_elders
2. get_active_event
3. get_event_detail
4. get_event_timeline
5. submit_elder_feedback
6. request_emergency_help
7. record_device_action
8. close_event
```

这个顺序很重要，因为后续工具需要用到前面工具返回的真实 `event_id`。

## 七、工具试运行参数示例

### 1. list_elders

用于验证 MCP 是否基本可用。

```json
{}
```

### 2. get_active_event

查询某位老人当前最新待处理事件。

```json
{
  "elder_id": "E001"
}
```

返回结果中会包含真实事件 ID，例如：

```text
evt_dd63a029ac44
```

后面的工具都应该使用这个真实 ID。

### 3. get_event_detail

```json
{
  "event_id": "evt_dd63a029ac44"
}
```

### 4. get_event_timeline

```json
{
  "event_id": "evt_dd63a029ac44"
}
```

### 5. submit_elder_feedback

老人说“我去一下洗手间”时：

```json
{
  "event_id": "evt_dd63a029ac44",
  "feedback_type": "bathroom",
  "original_text": "我去一下洗手间",
  "elder_id": "E001"
}
```

老人说“我没事”时：

```json
{
  "event_id": "evt_dd63a029ac44",
  "feedback_type": "ok",
  "original_text": "我没事",
  "elder_id": "E001"
}
```

老人说“我头晕”时：

```json
{
  "event_id": "evt_dd63a029ac44",
  "feedback_type": "dizzy",
  "original_text": "我有点头晕",
  "elder_id": "E001"
}
```

当前支持的 `feedback_type`：

```text
ok
bathroom
drink
dizzy
need_help
```

### 6. request_emergency_help

老人明确表达需要帮助时：

```json
{
  "event_id": "evt_dd63a029ac44",
  "original_text": "我需要帮助",
  "elder_id": "E001"
}
```

### 7. record_device_action

记录设备动作，例如打开夜灯：

```json
{
  "event_id": "evt_dd63a029ac44",
  "action": "open_night_light",
  "device_id": "tuya-light-demo",
  "result": "success"
}
```

当前这个工具主要用于记录动作。后续接入真实涂鸦设备控制 API 后，可以让它真正控制设备。

### 8. close_event

关闭事件：

```json
{
  "event_id": "evt_dd63a029ac44"
}
```

## 八、重要：不要手写假的 event_id

不要直接写：

```text
EVT-001
```

这只是示例编号，不存在于数据库里。

如果试运行工具时报：

```json
{
  "result": "There was an error executing the tool. The tool returned: Error executing tool submit_elder_feedback: event not found: EVT-001"
}
```

说明：

```text
1. 涂鸦已经成功连到了 MCP
2. MCP 工具已经被调用
3. 失败原因只是 event_id 不存在
```

正确流程是：

```text
先调用 get_active_event
拿返回结果里的 event.id
再调用 submit_elder_feedback / get_event_detail / close_event
```

## 九、智能体对话配置建议

智能体的工具调用逻辑可以按下面规则配置或通过提示词约束。

老人说：

```text
我没事
```

智能体应：

```text
1. 调用 get_active_event
2. 调用 submit_elder_feedback，feedback_type=ok
3. 回复：好的，已记录您当前安全。
```

老人说：

```text
我去洗手间
```

智能体应：

```text
1. 调用 get_active_event
2. 调用 submit_elder_feedback，feedback_type=bathroom
3. 回复：好的，已为您记录，会继续关注您是否安全回床。
```

老人说：

```text
我有点头晕
```

智能体应：

```text
1. 调用 get_active_event
2. 调用 submit_elder_feedback，feedback_type=dizzy
3. 必要时调用 request_emergency_help
4. 回复：我已记录并提醒家属关注，请您先坐稳或躺好。
```

老人说：

```text
帮帮我 / 我摔倒了 / 我起不来
```

智能体应：

```text
1. 调用 get_active_event
2. 调用 request_emergency_help
3. 回复：我已经发起帮助请求，请您保持安全姿势等待家属或护理人员确认。
```

## 十、比赛 MVP 推荐场景

最适合展示的场景是“夜间离床照护闭环”：

```text
1. 睡眠带或雷达检测到老人夜间离床
2. 后端或演示按钮创建 Guardian case
3. Guardian Agent 判断风险，暂不直接报警
4. Agent 调用或记录涂鸦夜灯场景
5. 涂鸦智能体询问老人：您是去洗手间，还是需要帮助？
6. 老人反馈：我去洗手间
7. Agent 记录反馈，进入观察
8. 如果长时间未回床，事件升级
9. Web 看板展示完整时间线
```

这个场景能同时展示：

```text
真实 IoT 信号接入
Agent 风险判断
涂鸦设备联动
老人语音确认
风险升级
Web 可解释看板
```

## 十一、当前踩过的坑

### 1. MCP 配置框不是工具参数框

错误示例：

```json
{
  "elder_id": "E001",
  "event_id": "EVT-001"
}
```

正确示例：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://你的公网地址/mcp?key=你的MCP访问密钥"
    }
  }
}
```

### 2. 涂鸦不接受 HTTP

涂鸦 MCP 必须使用 HTTPS。

不能填：

```text
http://服务器IP:8000/mcp
```

需要填：

```text
https://公网HTTPS域名/mcp?key=xxx
```

### 3. 涂鸦不允许 headers

所以我们不能在涂鸦 MCP 配置中写 `Authorization` header，只能把 key 放到 URL query 里。

### 4. 临时公网地址会变化

如果当前使用的是 `trycloudflare.com` 临时地址，那么 cloudflared 通道重启后地址可能变化。地址变化后，涂鸦 MCP 配置也要更新。

正式比赛或长期开发建议使用固定域名和 HTTPS。

## 十二、当前阶段与下一阶段

当前阶段：

```text
涂鸦智能体
  -> 临时 HTTPS 公网通道
  -> Guardian MCP
  -> SQLite 演示数据
```

下一阶段：

```text
涂鸦智能体
  -> 固定 HTTPS 域名
  -> Guardian MCP
  -> hjky-server / MySQL / MQTT
  -> Web 看板
```

最终目标：

```text
设备信号进入系统
  -> Guardian Agent 创建 case
  -> 涂鸦智能体与老人确认
  -> Guardian Agent 更新状态
  -> Web 看板展示完整闭环
```

