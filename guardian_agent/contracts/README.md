# Guardian Agent 阶段 0 契约说明

本目录是 Guardian Agent 第一阶段的“统一约定中心”。阶段 0 只冻结协议和验收规则，不实现状态机、REST 接口、页面、语音或涂鸦调用。

后续开发如需改变字段、状态、意图或场景，必须先修改这里的契约并更新评测集，不能只在某个业务文件里临时增加字符串。

## 1. 文件位置与权威性

| 内容 | 权威文件 | 用途 |
| --- | --- | --- |
| GuardianMessage 1.0 | `guardian_message_v1.schema.json` | 规定模拟信号与未来真实设备信号的统一格式 |
| 起夜状态枚举 | `../agent/contracts.py` 的 `NightEventStatus` | 规定一件起夜事件可以处于哪些状态 |
| 老人意图枚举 | `../agent/contracts.py` 的 `ElderIntent` | 规定老人自然语言最终要归一成哪些业务含义 |
| 事件类型枚举 | `../agent/contracts.py` 的 `GuardianEventType` | 规定统一入口能够接收哪些事件 |
| 六个核心场景 | `scenarios_v1.json` | 规定模拟器第一批必须支持的场景和期望结果 |
| night-turn 请求 | `night_turn_request_v1.schema.json` | 规定语音转写文字如何提交给 Agent |
| night-turn 响应 | `night_turn_response_v1.schema.json` | 规定 Agent 判断完成后返回什么 |
| 老人回答评测集 | `../evals/night_turn_cases_v1.json` | 检验意图、追问和风险结果是否符合约定 |
| 自动一致性检查 | `../tests/test_phase0_contracts.py` | 防止上述文件互相矛盾 |

## 2. 什么是 GuardianMessage 1.0

GuardianMessage 是设备或模拟器进入 Guardian Agent 前的统一信封。它解决的问题是：睡眠带、雷达、模拟器和未来涂鸦设备的原始格式不同，但 Agent 不应该为每一种来源重写业务逻辑。

例如当前模拟器与未来睡眠带都先转换成：

```json
{
  "schema_version": "1.0",
  "message_id": "sleep-E001-20260715-001",
  "source_system": "simulator",
  "device_type": "sleep_band",
  "device_id": "SLEEP001",
  "elder_id": "E001",
  "event_type": "LEAVE_BED",
  "occurred_at": "2026-07-15T02:13:20+08:00",
  "data": {
    "no_body_seconds": 180,
    "location": "bedroom"
  },
  "raw_payload": {
    "scenario_code": "normal_bathroom"
  }
}
```

其中：

- `message_id` 用于幂等，避免同一条 MQTT 消息重复创建事件。
- `source_system` 表示来自模拟器、MQTT 或设备回调。
- `event_type` 表示标准化后的事件含义。
- `data` 是 Agent 真正使用的标准字段。
- `raw_payload` 保留原始信号，便于排错和审计。

## 3. 什么是起夜状态枚举

“状态”表示一件起夜事件当前处理到了哪一步，不是老人说了什么。

| 状态 | 含义 |
| --- | --- |
| `NEW` | 刚收到信号，尚未处理 |
| `WAITING_ELDER_CONFIRM` | 已询问老人，等待回答 |
| `CLARIFYING` | 回答不明确，正在追问 |
| `MONITORING_RETURN` | 老人去厕所或喝水，等待返床 |
| `WAITING_FAMILY_CONFIRM` | 存在明显风险，等待子女确认 |
| `ESCALATED` | 跌倒等紧急情况已升级 |
| `CLOSED` | 已确认安全或返床，事件结束 |

状态由 Guardian 状态机改变，LLM 不能随意创造新状态。

## 4. 什么是意图枚举

“意图”表示 Agent 对老人一句话的结构化理解，不等于事件状态。

例如“我去趟厕所”对应意图 `bathroom`，状态机再把事件从 `WAITING_ELDER_CONFIRM` 更新为 `MONITORING_RETURN`。

| 意图 | 含义 | 通常结果 |
| --- | --- | --- |
| `ok` | 明确表示安全且无不适 | 可关闭或继续短时观察 |
| `bathroom` | 去卫生间 | 观察返床 |
| `drink` | 起床喝水 | 观察返床 |
| `medication` | 起床找药或吃药 | 先追问药物和当前不适 |
| `dizzy` | 头晕、站不稳 | 风险升级 |
| `pain` | 胸痛、明显疼痛 | 风险升级 |
| `fall` | 已摔倒或疑似摔倒 | 紧急升级 |
| `need_help` | 主动求助、无法站立、呼吸困难 | 风险升级 |
| `unknown` | 空白或无法判断 | 追问一次 |

危险含义优先。例如“我没事，就是有点晕”必须判为 `dizzy`，不能判为 `ok`。

## 5. 六个核心模拟场景

第一批只冻结六个场景：正常上厕所、喝水、头晕、主动求助、无响应和跌倒。`RETURN_TO_BED` 是正常场景的后续收尾信号，不单独占用一个核心场景。

完整输入和期望结果位于 `scenarios_v1.json`。阶段 1 的模拟器必须读取或实现这些场景，页面不得直接修改事件状态。

## 6. 什么是 night-turn

night-turn 表示起夜事件中的“一轮老人回答处理”：

```text
STT 得到文字
  -> night-turn 请求
  -> Agent 判断意图
  -> 状态机处理
  -> night-turn 响应
  -> TTS 播放 reply_text
```

请求只描述老人是谁、当前事件、会话、原话和来源；响应返回意图、置信度、是否追问、事件新状态、风险级别和播报文字。

阶段 0 只确定输入输出格式，暂不新增 `/api/v1/guardian/conversations/night-turn` 接口。

## 7. 什么是老人回答评测集

评测集不是训练数据，而是一组带标准答案的验收题。每条数据包含老人原话、期望意图、期望状态、是否必须升级以及是否需要追问。

以后无论使用本地规则、涂鸦 LLM 还是其他模型，都运行同一份评测集。模型可以变化，业务验收标准保持不变。

运行契约检查：

```powershell
python -m unittest discover -s tests -p "test_phase0_contracts.py" -v
```
