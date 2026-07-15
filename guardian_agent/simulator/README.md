# 阶段 1：统一模拟信号入口

本目录只负责根据 `contracts/scenarios_v1.json` 生成 GuardianMessage 1.0。场景名称、输入步骤和期望结果不在 Python 中重复维护。

## 1. 只查看场景消息，不写数据库

```powershell
cd D:\wlw\guardian_agent_prototype_new\guardian_agent
python -m simulator.cli normal_bathroom --elder-id E001 --dry-run
```

可用场景：

```text
normal_bathroom
normal_drink
dizzy
need_help
no_response
fall_detected
```

## 2. 通过统一处理函数运行场景

```powershell
python -m simulator.cli normal_bathroom --elder-id E001
```

`--reset` 会重置演示 SQLite，仅在明确需要恢复模拟数据时使用：

```powershell
python -m simulator.cli fall_detected --elder-id E003 --reset
```

## 3. 通过 REST 入口提交

先启动服务：

```powershell
python server.py
```

统一入口：

```text
POST http://127.0.0.1:8765/api/v1/guardian/messages
```

请求体必须符合 `contracts/guardian_message_v1.schema.json`。缺少必填字段、使用未知字段、时间不带时区或枚举值错误时，入口会拒绝消息。

同一个 `message_id` 重复提交时：

- 不会再次触发状态机；
- 不会创建第二个事件；
- 返回 `duplicate: true`；
- 返回第一次处理得到的事件和动作结果。

## 4. 数据保存位置

- 完整标准消息和 `raw_payload`：SQLite 的 `raw_messages.payload_json`。
- 第一次处理结果：`raw_messages.result_json`。
- 处理状态：`raw_messages.processed_status`。
- 与事件相关的标准输入：事件 `decisions` 时间线，类型为 `input`。

## 5. 运行测试

```powershell
python -m unittest discover -s tests -p "test_guardian_message*.py" -v
```

阶段 1 不负责老人自然语言意图判断，也不负责连接真实 MQTT、睡眠带或雷达。后续适配器只需把真实消息转换为同一个 GuardianMessage 1.0，再调用统一入口。

