# Guardian MCP 接入涂鸦与公网部署 README

> **2026-07-15 版本提示**：本地新版 MCP 已调整为 `list_elders`、`night_care_workflow`、`health_report_workflow` 三个聚合工具，并补充了模拟 Guardian 场景及日报周报流程。当前公网冒烟测试仍返回旧工具版本，必须先发布本地更新包并只重启 `guardian-mcp.service`，再在涂鸦平台刷新工具列表。新版 Agent Prompt 和搭建步骤见 `guardian_agent/tuya/GUARDIAN_CARE_AGENT_PROMPT.md` 与 `guardian_agent/tuya/TUYA_AGENT_SETUP.md`。

这份文档给团队成员使用，说明当前 Guardian MCP 是什么、涂鸦平台应该怎么配置、MCP 里有哪些工具，以及它后续如何和 hjky-server、MQTT、Web 看板配合。

## 先看这里：当前涂鸦 MCP 已经部署好了

当前 Guardian MCP 已经部署在项目现有的公网 Ubuntu 服务器上，并且已经通过临时 HTTPS 通道暴露给涂鸦平台。

### 当前部署信息（团队共用）

| 项目 | 当前值 | 用途 |
| --- | --- | --- |
| 公网服务器 IP | `121.43.247.31` | 使用 MobaXterm / SSH 登录并部署 Agent 的服务器；也是现有康养后端所在服务器。 |
| SSH 登录账号 | `root` | 上传代码、查看日志、重启 MCP 服务时使用。 |
| SSH 登录密码 |  Ninelab2025| 这是服务器登录密码，不是涂鸦 MCP 密钥。 |
| Agent 部署目录 | `/opt/guardian-agent` | 服务器上正在运行的 Guardian Agent 代码目录。 |
| MCP 服务 | `guardian-mcp.service` | 运行 Agent/MCP；日常更新后只重启它。 |
| 公网 HTTPS 通道 | `guardian-mcp-tunnel.service` | 将服务器内部的 MCP 转为涂鸦可访问的 HTTPS 地址；日常更新不要重启它。 |
| 当前涂鸦公网地址 | `https://wesley-anthony-motorcycles-fitting.trycloudflare.com/mcp` | 涂鸦平台访问 Guardian MCP 的基础地址。 |
| MCP 访问密钥 | 已写入下方“涂鸦 MCP 配置 JSON”的 `key` 参数 | 用于涂鸦访问 MCP，不等同于服务器 SSH 密码。 |

换句话说，团队日常更新操作的目标服务器就是：`root@121.43.247.31`；代码更新到该服务器的 `/opt/guardian-agent` 目录即可。

日常开发时，**不需要每次更新 Agent 代码都重新配置公网地址**。一般只需要：

```text
1. 更新服务器上的 /opt/guardian-agent 代码
2. 重启 guardian-mcp.service
3. 涂鸦平台继续使用同一个 MCP 配置
```

这里有一个必须遵守的边界：**只重启 `guardian-mcp.service`，不要重启 `guardian-mcp-tunnel.service`。** 前者是 Agent 程序本身；后者保存当前临时公网通道。只更新前者，涂鸦端当前的公网 URL 和 MCP 密钥都不需要修改。

更完整的日常更新步骤如下。

### 日常 Agent 更新 SOP

适用场景：

```text
改了 mcp_server.py
改了 guardian_tools.py
改了 agent/ 里的业务逻辑
新增或修改 MCP 工具
更新 SQLite 演示数据
更新 static/ 原型页面
```

这些情况通常只需要更新 MCP 服务本体，不需要重新配置公网，也不需要重启 `guardian-mcp-tunnel.service`。

#### 1. 先在本地确认新版代码可运行

进入本地新版 Agent 目录：

```powershell
cd "D:\wlw\guardian_agent_prototype_new\guardian_agent"
```

运行单元测试：

```powershell
python -m unittest discover -s tests -p test_guardian_tools.py -v
```

做语法检查：

```powershell
python -m py_compile mcp_server.py guardian_tools.py server.py agent\db.py agent\night.py agent\health.py agent\memory.py agent\seed.py
```

如果这里失败，先修本地代码，不要部署到服务器。

#### 2. 打包新版代码

在本地 `D:\wlw` 目录执行打包。打包时建议排除缓存、日志、pid 文件：

```powershell
cd D:\wlw

$stage = "guardian_agent_update_stage"
if (Test-Path -LiteralPath $stage) {
  Remove-Item -LiteralPath $stage -Recurse -Force
}

New-Item -ItemType Directory -Path $stage | Out-Null

robocopy "guardian_agent_prototype_new\guardian_agent" $stage /E /XD __pycache__ /XF *.log *.pid *.pyc | Out-Null

tar -czf guardian_agent_update.tar.gz -C $stage .
```

生成的文件：

```text
D:\wlw\guardian_agent_update.tar.gz
```

#### 3. 上传到公网服务器

这里的服务器就是本 README 顶部列出的 `121.43.247.31`，登录账号为 `root`。上传目标建议放到：

```text
/tmp/guardian_agent_update.tar.gz
```

示例：

```powershell
scp D:\wlw\guardian_agent_update.tar.gz root@121.43.247.31:/tmp/guardian_agent_update.tar.gz
scp "D:\wlw\guardian_agent_update_20260715.tar.gz" root@121.43.247.31:/tmp/guardian_agent_update.tar.gz
```

如果使用 MobaXterm，也可以直接把 `guardian_agent_update.tar.gz` 拖到服务器 `/tmp` 目录。

#### 4. 在服务器上备份旧版本（需要使用MobaXterm）

SSH 登录服务器步骤：
1.打开MobaXterm
2. 打开一个本地终端
3.输入 ssh root@121.43.247.31 后回车
4.输入密码Ninelab2025


SSH 登录服务器后执行：

```bash
ts=$(date +%Y%m%d%H%M%S)
systemctl stop guardian-mcp.service

if [ -d /opt/guardian-agent ]; then
  mv /opt/guardian-agent /opt/guardian-agent.backup.$ts
fi
```

这样旧版本会备份成：

```text
/opt/guardian-agent.backup.时间戳
```

如果新版有问题，可以用这个目录回滚。

#### 5. 解压新版代码到 /opt/guardian-agent

继续在服务器上执行：

```bash
mkdir -p /opt/guardian-agent
tar -xzf /tmp/guardian_agent_update.tar.gz -C /opt/guardian-agent
chown -R root:root /opt/guardian-agent
```

如果依赖没变，通常不需要重新安装依赖。  
如果 `requirements.txt` 改过，执行：

```bash
if [ ! -d /opt/guardian-agent/.venv ]; then
  python3 -m venv /opt/guardian-agent/.venv
fi

/opt/guardian-agent/.venv/bin/python -m pip install -r /opt/guardian-agent/requirements.txt
```

#### 6. 重启 MCP 服务

只重启 MCP：

```bash
systemctl start guardian-mcp.service
systemctl is-active guardian-mcp.service
```

看到：

```text
active
```

说明 MCP 服务已经起来。

一般不要重启：

```bash
guardian-mcp-tunnel.service
```

因为 tunnel 一重启，`trycloudflare.com` 临时公网地址可能变化；地址一变，涂鸦 MCP 配置里的 URL 就要更新。

#### 7. 验证公网 MCP 是否正常

先确认 tunnel 还活着：

```bash
systemctl is-active guardian-mcp-tunnel.service
```

应该返回：

```text
active
```

再用 MCP smoke test 验证工具列表：

```bash
export GUARDIAN_MCP_API_KEY=$(grep "^GUARDIAN_MCP_API_KEY=" /etc/guardian-agent.env | cut -d= -f2-)
export GUARDIAN_MCP_AUTH_MODE=query
export GUARDIAN_MCP_TEST_URL=https://wesley-anthony-motorcycles-fitting.trycloudflare.com/mcp

cd /opt/guardian-agent

# 发布包不会携带 Windows 虚拟环境；服务器首次部署或目录被替换后需创建。
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python tests/mcp_smoke.py
```

正常会看到：

```text
MCP initialization: OK
Discovered tools: ...
get_active_event: OK
```

如果新增了 MCP 工具，要确认 `Discovered tools` 里已经出现新工具名。

#### 8. 在涂鸦平台刷新工具列表

如果只是更新代码、修逻辑、改返回内容，涂鸦 MCP 配置 JSON 不用改。

如果新增了工具，但涂鸦页面还只显示旧工具：

```text
1. 进入涂鸦 MCP 服务详情页
2. 重新保存同一段 MCP JSON
3. 切换到“工具”页刷新
4. 退出该 MCP 服务页面再重新进入
5. 仍不更新时，用同一段 JSON 新建一个自定义 MCP 服务
```

这是涂鸦平台工具 schema 缓存问题，不是公网部署问题。

#### 9. 什么情况下才需要重新配置公网

只有这些情况才需要重新获取公网地址或修改涂鸦 JSON：

```text
服务器重启
guardian-mcp-tunnel.service 被重启
cloudflared 临时通道失效
更换服务器
改用正式域名/HTTPS
修改 GUARDIAN_MCP_API_KEY
```

普通 Agent 代码更新不需要重新配置公网。

#### 10. 快速回滚

如果新版部署后有问题，可以回滚到最近一次备份：

```bash
systemctl stop guardian-mcp.service

mv /opt/guardian-agent /opt/guardian-agent.failed.$(date +%Y%m%d%H%M%S)
mv /opt/guardian-agent.backup.时间戳 /opt/guardian-agent

systemctl start guardian-mcp.service
systemctl is-active guardian-mcp.service
```

回滚也不需要重启 `guardian-mcp-tunnel.service`，所以公网地址通常不会变化。

只有下面几种情况才需要重新处理公网地址：

```text
1. guardian-mcp-tunnel.service 被重启
2. 服务器重启导致 Cloudflare 临时通道地址变化
3. 临时 trycloudflare 地址失效
4. 换服务器、换域名、改成正式 HTTPS
```

当前涂鸦平台 MCP 配置代码如下，直接填到涂鸦的 MCP 服务配置框即可：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://wesley-anthony-motorcycles-fitting.trycloudflare.com/mcp?key=f50f7c26dda9b94d4dc986f634b8db3efab084e2e221a201542b813ef351851e"
    }
  }
}
```

配置位置：

```text
涂鸦开发者平台 -> MCP 管理 -> 自定义 MCP 服务 -> Guardian Care MCP -> 服务配置
```

接入方式：

```text
Streamable HTTP
```

保存后进入“工具”页试运行即可。当前公网 smoke test 已验证通过，可以发现 13 个工具。

如果只是更新 MCP 代码或新增工具，通常不用改上面的 JSON。部署新版代码后，在涂鸦工具页刷新或重新进入 MCP 服务即可看到新版工具。

## 一、当前项目位置

本地代码目录：

```text
D:\wlw\guardian_agent_prototype
```

服务器部署目录：

```text
/opt/guardian-agent
```

当前涂鸦平台访问的是服务器上的 MCP，不是电脑本地 MCP。

## 二、MCP 在系统里的位置

MCP 是“涂鸦智能体调用我们系统能力”的工具层。

可以这样理解：

```text
涂鸦智能体
  -> Guardian MCP
  -> guardian_tools.py
  -> Guardian Agent 业务逻辑
  -> SQLite / 后续 hjky-server
```

MCP 不直接替代 Java 后端，也不替代 Web 前端。它的作用是把涂鸦智能体里的自然语言意图，转换成我们系统内部可执行的工具调用。

例如：

```text
老人说：“我去洗手间”

涂鸦智能体：
  1. 调用 get_active_event 找到当前事件
  2. 调用 submit_elder_feedback 写入老人反馈

Guardian Agent：
  1. 更新 case 状态
  2. 记录 timeline
  3. 返回处理结果
```

## 三、目录结构说明

重点文件如下：

```text
guardian_agent_prototype/
  mcp_server.py
    MCP 服务入口，定义涂鸦能看到和调用的工具。

  guardian_tools.py
    MCP 工具背后的业务函数，负责查询事件、提交反馈、关闭事件等。

  agent/
    Guardian Agent 核心逻辑。

  agent/night.py
    夜间离床、老人反馈、风险升级、关闭事件等逻辑。

  agent/db.py
    SQLite 表结构。

  agent/seed.py
    演示数据初始化。

  guardian_agent.sqlite3
    当前调试数据库。

  tests/
    工具函数测试和 MCP smoke test。

  deploy/
    服务器 systemd 服务文件。

  static/
    原型演示页面资源。

  README.md
    项目自身说明。
```

## 四、当前 MCP 提供的工具

当前 MCP 提供 13 个工具。

### 1. list_elders

查询系统中的老人列表。

适合用于：

```text
1. 验证 MCP 是否连通
2. 给智能体查询可服务的老人
```

### 2. get_active_event

查询某位老人最新的待处理事件。

典型参数：

```json
{
  "elder_id": "E001"
}
```

这是很多后续工具的第一步，因为后续工具需要真实 `event_id`。

### 3. get_event_detail

查询某个事件详情。

典型参数：

```json
{
  "event_id": "evt_dd63a029ac44"
}
```

### 4. get_event_timeline

查询事件时间线。

用于查看：

```text
1. Agent 做过哪些判断
2. 调用过哪些工具
3. 老人反馈过什么
4. 事件是否升级或关闭
```

### 5. submit_elder_feedback

提交老人反馈。

典型参数：

```json
{
  "event_id": "evt_dd63a029ac44",
  "feedback_type": "bathroom",
  "original_text": "我去一下洗手间",
  "elder_id": "E001"
}
```

当前支持的反馈类型：

```text
ok          老人表示没事
bathroom    老人表示去洗手间
drink       老人表示喝水
dizzy       老人表示头晕
need_help   老人表示需要帮助
```

### 6. request_emergency_help

请求紧急帮助。

适用于：

```text
老人说“帮帮我”
老人说“我摔倒了”
老人说“我起不来”
老人说“我头晕，需要帮助”
```

### 7. record_device_action

记录设备动作。

例如：

```text
打开夜灯
执行涂鸦场景
关闭设备
调整亮度
```

当前主要是写入事件时间线。后续可以扩展为真正调用涂鸦设备 API。

### 8. close_event

关闭事件。

适用于：

```text
老人确认安全
家属确认处理完成
演示流程结束
```

### 9. get_daily_report

获取某位老人最近一次健康日报。

典型参数：

```json
{
  "elder_id": "E001"
}
```

适用于：

```text
涂鸦智能体回答“今天健康情况怎么样”
Web 看板或智能体查询最近健康摘要
```

### 10. generate_daily_report

重新生成某位老人的健康日报。

典型参数：

```json
{
  "elder_id": "E001",
  "report_date": "2026-07-14"
}
```

`report_date` 可以留空，留空时由系统按当前日期或最近体征生成。

适用于：

```text
有新体征数据后，主动生成当天健康分析
```

### 11. get_weekly_report

获取某位老人最近一次健康周报。

典型参数：

```json
{
  "elder_id": "E001"
}
```

适用于：

```text
涂鸦智能体回答“这周健康趋势怎么样”
```

### 12. generate_weekly_report

重新生成某位老人的健康周报。

典型参数：

```json
{
  "elder_id": "E001",
  "week_end": "2026-07-14"
}
```

`week_end` 可以留空，留空时由系统自动取当前日期附近的周期。

适用于：

```text
根据最近一周体征数据重新分析趋势
```

### 13. get_recent_vitals

获取老人最近体征数据。

典型参数：

```json
{
  "elder_id": "E001",
  "limit": 7
}
```

返回内容包括体温、心率、血压、血糖、血氧、睡眠、步数等模拟数据。

适用于：

```text
涂鸦智能体查询“最近几次体征”
健康日报/周报生成前的数据确认
```

## 五、当前数据存储

当前调试阶段使用 SQLite。

本地 SQLite：

```text
D:\wlw\guardian_agent_prototype\guardian_agent.sqlite3
```

服务器 SQLite：

```text
/opt/guardian-agent/guardian_agent.sqlite3
```

涂鸦调用的是服务器 MCP，所以读写的是服务器 SQLite。

SQLite 里主要表：

```text
elders
devices
events
decisions
notifications
raw_messages
```

后续正式接入时，建议逐步从：

```text
MCP -> SQLite
```

改成：

```text
MCP -> hjky-server REST API -> MySQL
```

或者：

```text
MCP -> 后端服务层 -> MySQL / MQTT / 设备数据
```

## 六、和其他模块怎么配合

### 1. 和涂鸦平台

涂鸦负责智能体入口和未来设备生态。

```text
老人说话
  -> 涂鸦智能体理解意图
  -> 涂鸦调用 Guardian MCP 工具
  -> Guardian Agent 更新 case
  -> 涂鸦把结果反馈给老人
```

### 2. 和 Guardian Agent

Guardian Agent 是事件中枢，负责：

```text
1. 风险事件建模
2. case 状态流转
3. timeline 记录
4. 风险升级
5. 事件关闭
```

MCP 只是入口层，真正的业务逻辑仍在 Guardian Agent。

### 3. 和 hjky-server

当前还没有正式打通 Java 后端，当前 MCP 背后是 SQLite 演示数据。

后续建议新增或复用 hjky-server 接口：

```text
GET  /guardian/elders
GET  /guardian/events/active?elderId=E001
GET  /guardian/events/{eventId}
GET  /guardian/events/{eventId}/timeline
POST /guardian/events/{eventId}/feedback
POST /guardian/events/{eventId}/emergency
POST /guardian/events/{eventId}/device-actions
POST /guardian/events/{eventId}/close
```

然后把 `guardian_tools.py` 中的 SQLite 读写替换成 HTTP 调用 hjky-server。

### 4. 和 MQTT

MQTT 更适合承担设备上报通道。

正式链路建议：

```text
睡眠带 / 雷达 / SOS
  -> MQTT
  -> hjky-server
  -> 创建或更新 Guardian case
  -> Web 看板展示
  -> 涂鸦智能体通过 MCP 查询和反馈
```

当前 MCP 调试阶段不依赖 MQTT。

### 5. 和 Web 看板

Web 看板负责展示：

```text
1. 风险卡片
2. 事件详情
3. Agent 决策时间线
4. 老人反馈
5. 事件关闭状态
```

最终应该让 Web 看板和 MCP 都读写同一份后端数据，这样涂鸦智能体提交反馈后，看板能同步变化。

## 七、本地运行 MCP

进入项目目录：

```powershell
cd D:\wlw\guardian_agent_prototype
```

创建 Python 虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -r requirements.txt
```

设置环境变量并运行：

```powershell
$env:GUARDIAN_MCP_HOST = "127.0.0.1"
$env:GUARDIAN_MCP_PORT = "8000"
$env:GUARDIAN_MCP_API_KEY = "dev-secret"
python mcp_server.py
```

本地服务地址：

```text
http://127.0.0.1:8000/mcp
```

注意：本地 HTTP 地址不能直接填到涂鸦平台，因为涂鸦需要公网 HTTPS。

## 八、为什么需要公网 HTTPS 地址

涂鸦平台是云端服务，它要主动访问我们的 MCP。

所以 MCP 地址必须满足：

```text
1. 公网可访问
2. HTTPS
3. 能访问 /mcp 路径
4. 带有效鉴权 key
```

不能使用：

```text
http://127.0.0.1:8000/mcp
http://localhost:8000/mcp
http://服务器IP:8000/mcp
```

应该使用：

```text
https://你的域名/mcp?key=xxx
```

## 九、方式 A：使用 Cloudflare 临时公网通道

这是当前调试使用的方式，优点是快，不需要先申请 HTTPS 证书。缺点是地址会变化。

### 1. 服务器上运行 MCP

MCP 监听服务器本机：

```text
127.0.0.1:8000
```

这样外部不能直接访问 8000 端口，只有 cloudflared 能从服务器本机转发。

### 2. 安装 cloudflared

Ubuntu 服务器上安装 cloudflared。安装完成后应能执行：

```bash
cloudflared --version
```

### 3. 启动临时通道

手动调试可以执行：

```bash
cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8000
```

启动后日志里会出现类似：

```text
https://xxxx.trycloudflare.com
```

最终填到涂鸦里的地址是：

```text
https://xxxx.trycloudflare.com/mcp?key=你的MCP访问密钥
```

### 4. 当前服务器上的 systemd 服务

当前服务器上已经配置了两个服务：

```text
guardian-mcp.service
guardian-mcp-tunnel.service
```

`guardian-mcp.service` 负责运行 MCP：

```text
127.0.0.1:8000
```

`guardian-mcp-tunnel.service` 负责运行 cloudflared 临时通道：

```text
https://xxxx.trycloudflare.com -> http://127.0.0.1:8000
```

常用命令：

```bash
systemctl status guardian-mcp
systemctl status guardian-mcp-tunnel
systemctl restart guardian-mcp
systemctl restart guardian-mcp-tunnel
```

### 5. 查看当前临时公网地址

这里说的“服务器”，指的是当前已经部署 Guardian MCP 的那台公网 Ubuntu 服务器，也就是：

```text
MobaXterm 里连接的那台康养/后端服务器
Guardian MCP 部署目录：/opt/guardian-agent
MCP systemd 服务名：guardian-mcp.service
临时公网通道服务名：guardian-mcp-tunnel.service
```

如果队友不知道具体是哪台服务器，可以先看项目交接资料里的服务器登录信息，或在 MobaXterm 里找已有的康养服务器连接。登录服务器后，先确认服务是否存在：

```bash
systemctl status guardian-mcp
systemctl status guardian-mcp-tunnel
```

如果能看到这两个服务，说明当前就在正确服务器上。

查看当前临时公网地址，在这台服务器上执行：

```bash
journalctl -u guardian-mcp-tunnel.service -b --no-pager \
  | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
  | tail -n 1
```

输出的就是当前公网地址。

### 6. 查看 MCP 访问密钥

MCP 访问密钥就是涂鸦 URL 里 `key=` 后面的值。

当前服务器上，密钥保存在：

```text
/etc/guardian-agent.env
```

登录同一台公网 Ubuntu 服务器后执行：

```bash
cat /etc/guardian-agent.env
```

找到这一行：

```text
GUARDIAN_MCP_API_KEY=这里就是MCP访问密钥
```

也可以只输出 key 这一行：

```bash
grep '^GUARDIAN_MCP_API_KEY=' /etc/guardian-agent.env
```

把公网地址和 key 拼起来，就是涂鸦 MCP 配置里要用的 URL：

```text
https://xxxx.trycloudflare.com/mcp?key=这里填GUARDIAN_MCP_API_KEY的值
```

完整涂鸦配置示例：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://xxxx.trycloudflare.com/mcp?key=这里填GUARDIAN_MCP_API_KEY的值"
    }
  }
}
```

注意：如果使用的是临时 `trycloudflare.com` 地址，公网地址可能变化；但 `GUARDIAN_MCP_API_KEY` 通常不会因为重启而变化，除非有人手动修改 `/etc/guardian-agent.env`。

### 7. 什么操作会导致地址变化

会导致地址变化的情况：

```text
1. 重启服务器
2. 重启 guardian-mcp-tunnel.service
3. 停止再启动 cloudflared
4. cloudflared 异常退出后自动重启
```

通常不会导致地址变化的情况：

```text
1. 重启 guardian-mcp.service
2. 重启 hjky-server
3. 重启 Nginx
4. 修改 SQLite
5. 修改 MCP 代码后只重启 MCP 服务
```

如果临时公网地址变化，需要重新进入涂鸦平台修改 MCP 配置。

## 十、方式 B：使用正式域名 + Nginx + HTTPS

这是比赛或长期开发更推荐的方式。优点是地址稳定，缺点是需要域名和 HTTPS 证书配置。

目标地址类似：

```text
https://guardian-mcp.example.com/mcp?key=xxx
```

### 1. 准备域名

准备一个域名或子域名，例如：

```text
guardian-mcp.example.com
```

在 DNS 服务商处添加 A 记录：

```text
guardian-mcp.example.com -> 服务器公网 IP
```

等待 DNS 生效。

### 2. MCP 仍然监听本机

MCP 不需要直接暴露公网端口，仍然监听：

```text
127.0.0.1:8000
```

这样更清晰：

```text
公网 HTTPS
  -> Nginx
  -> 127.0.0.1:8000
  -> Guardian MCP
```

### 3. Nginx 反向代理示例

可以新增一个 Nginx server：

```nginx
server {
    listen 80;
    server_name guardian-mcp.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

检查配置：

```bash
nginx -t
```

重载 Nginx：

```bash
systemctl reload nginx
```

### 4. 配置 HTTPS 证书

推荐使用 certbot 申请 Let's Encrypt 证书：

```bash
certbot --nginx -d guardian-mcp.example.com
```

完成后，访问：

```text
https://guardian-mcp.example.com/mcp?key=xxx
```

这就是涂鸦平台里最终要填的稳定地址。

## 十一、方式 C：Cloudflare Named Tunnel

如果团队使用 Cloudflare 管理域名，也可以使用 Named Tunnel。

它和临时 `trycloudflare.com` 的区别是：

```text
临时 tunnel
  地址随机，重启可能变化。

Named Tunnel
  地址固定，可以绑定自己的域名。
```

典型链路：

```text
https://guardian-mcp.example.com
  -> Cloudflare Named Tunnel
  -> 服务器 127.0.0.1:8000
  -> Guardian MCP
```

这种方式也适合长期调试，但需要 Cloudflare 账号和域名配置。

## 十二、涂鸦 MCP 配置最终格式

无论使用临时通道还是正式域名，涂鸦里的 JSON 都是同一种结构：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://你的公网HTTPS地址/mcp?key=你的MCP访问密钥"
    }
  }
}
```

不要写：

```json
{
  "url": "https://xxx/mcp",
  "headers": {
    "Authorization": "Bearer xxx"
  }
}
```

涂鸦会拒绝 `headers`。

## 十三、如何验证 MCP 是否可用

### 1. 看服务状态

服务器上：

```bash
systemctl is-active guardian-mcp
systemctl is-active guardian-mcp-tunnel
```

两个都应该返回：

```text
active
```

如果使用正式 Nginx HTTPS，就不需要 `guardian-mcp-tunnel`。

### 2. 在涂鸦平台保存配置

如果 JSON 格式正确，涂鸦会提示保存成功。

### 3. 在涂鸦工具页试运行

先运行：

```json
{}
```

对应工具：

```text
list_elders
```

再运行：

```json
{
  "elder_id": "E001"
}
```

对应工具：

```text
get_active_event
```

拿到真实事件 ID 后，再测试：

```text
get_event_detail
submit_elder_feedback
close_event
```

## 十四、常见错误和解决方法

### 1. JSON 格式错误

原因通常是：

```text
1. 使用了中文引号
2. 少了逗号
3. 多了逗号
4. 把工具参数填进 MCP 服务配置
5. 没有使用 mcpServers 外层结构
```

正确格式：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://xxx/mcp?key=xxx"
    }
  }
}
```

### 2. MCP配置包含禁止使用的字段: headers

涂鸦不允许 `headers`，改成：

```text
https://xxx/mcp?key=xxx
```

### 3. event not found

报错示例：

```text
event not found: EVT-001
```

原因是事件 ID 不存在。

解决方法：

```text
先调用 get_active_event
使用返回结果里的 event.id
再调用 submit_elder_feedback
```

### 4. 连接失败

检查：

```text
1. 公网地址是否是 HTTPS
2. tunnel 是否还活着
3. MCP 服务是否 active
4. URL 是否包含 /mcp
5. URL 是否包含正确 key
6. 临时 trycloudflare 地址是否已经变化
```

## 十五、队友如何快速接手

### 1. 拿到代码

解压交接包后进入：

```text
guardian_agent_prototype
```

### 2. 本地跑 MCP

按本文“本地运行 MCP”步骤执行。

### 3. 如果要接入涂鸦

需要任选一种公网方式：

```text
方式 A：Cloudflare 临时 tunnel，最快
方式 B：正式域名 + Nginx + HTTPS，最稳定
方式 C：Cloudflare Named Tunnel，稳定且适合 Cloudflare 域名
```

### 4. 配置涂鸦 MCP

把公网 HTTPS 地址填进：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://公网HTTPS地址/mcp?key=访问密钥"
    }
  }
}
```

### 5. 试运行工具

先跑：

```text
list_elders
get_active_event
```

再跑需要 `event_id` 的工具。

## 十六、代码交接建议

为了让队友快速配置，可以直接发送打包文件。

建议包内包含：

```text
guardian_agent_prototype/
Guardian_Agent_涂鸦平台配置步骤.md
Guardian_MCP_涂鸦接入与模块协作说明.md
```

如果以“快速复现当前状态”为目标，可以连同以下运行文件一起发：

```text
guardian_agent.sqlite3
.env.tuya.local
.env.tuya.server
.tuya-mcp-config.server.json
.tuya-mcp-url.txt
```

这些文件能帮助队友快速理解当前调试状态。后续如果进入正式仓库或公开提交，再考虑清理密钥和临时地址。

## 十七、后续开发路线

第一阶段：

```text
保持 SQLite，继续打磨涂鸦智能体工具调用流程。
```

第二阶段：

```text
把 guardian_tools.py 从 SQLite 改成调用 hjky-server。
```

第三阶段：

```text
让 MQTT 或涂鸦真实设备事件进入 hjky-server，并自动创建 Guardian case。
```

第四阶段：

```text
使用正式域名和 HTTPS 替换临时 trycloudflare 地址。
```

第五阶段：

```text
Web 看板、涂鸦智能体、后端数据库统一读取同一份 case 数据。
```

最终目标：

```text
真实设备信号
  -> hjky-server / MQTT
  -> Guardian Agent 创建 case
  -> 涂鸦智能体确认老人状态
  -> Guardian Agent 更新状态和时间线
  -> Web 看板展示闭环
```
