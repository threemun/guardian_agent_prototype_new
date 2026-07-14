# 新版 Guardian Agent 配置说明

本目录是队友更新后的 Guardian Agent。实际项目根目录是：

```text
D:\wlw\guardian_agent_prototype(2)\guardian_agent
```

相比上一版，这一版保留了照护事件 MCP 工具，并新增了健康报告和亲情回忆相关能力。

## 先看这里：新版 Agent 已经部署到公网 MCP

新版 Agent 已经部署到公网服务器：

```text
/opt/guardian-agent
```

并且已经通过当前 Cloudflare 临时 HTTPS 通道接入涂鸦。涂鸦平台 MCP 配置代码如下：

```json
{
  "mcpServers": {
    "guardian-care-streamableHTTP": {
      "url": "https://wesley-anthony-motorcycles-fitting.trycloudflare.com/mcp?key=f50f7c26dda9b94d4dc986f634b8db3efab084e2e221a201542b813ef351851e"
    }
  }
}
```

日常更新新版 Agent 时，不需要每次重新配置公网。通常只需要：

```text
1. 把新版代码部署到服务器 /opt/guardian-agent
2. 重启 guardian-mcp.service
3. 涂鸦平台继续使用上面的 MCP 配置
```

只有当 `guardian-mcp-tunnel.service` 重启、服务器重启、临时地址失效、或者改用正式域名时，才需要重新获取公网地址并更新涂鸦配置。

## 一、我已补齐的配置

已经从上一版可用配置中补齐：

```text
guardian_agent/deploy/
guardian_agent/tools/
guardian_agent/start_tuya_debug.ps1
guardian_agent/stop_tuya_debug.ps1
guardian_agent/tests/mcp_smoke.py
guardian_agent/.env.tuya.local
guardian_agent/.env.tuya.server
guardian_agent/.tuya-mcp-config.server.json
guardian_agent/.tuya-mcp-url.txt
guardian_agent/.gitignore
```

外层也补充了团队交接 README：

```text
Guardian_Agent_涂鸦平台配置步骤.md
Guardian_MCP_涂鸦接入与模块协作说明.md
```

## 二、新版 MCP 工具

新版 MCP 当前包含 13 个工具：

```text
list_elders
get_active_event
get_event_detail
get_event_timeline
submit_elder_feedback
request_emergency_help
record_device_action
close_event
get_daily_report
generate_daily_report
get_weekly_report
generate_weekly_report
get_recent_vitals
```

前 8 个用于照护事件闭环，后 5 个用于健康日报、周报和最近体征查询。

## 三、本地运行

进入新版项目根目录：

```powershell
cd "D:\wlw\guardian_agent_prototype(2)\guardian_agent"
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

运行 MCP：

```powershell
$env:GUARDIAN_MCP_API_KEY="dev-secret"
$env:GUARDIAN_MCP_HOST="127.0.0.1"
$env:GUARDIAN_MCP_PORT="8000"
python mcp_server.py
```

MCP 地址：

```text
http://127.0.0.1:8000/mcp
```

本地地址不能直接填到涂鸦平台，涂鸦需要公网 HTTPS。

## 四、涂鸦调试

如果使用本机临时 tunnel，可以在新版项目根目录运行：

```powershell
.\start_tuya_debug.ps1
```

脚本会：

```text
1. 读取 .env.tuya.local 中的 GUARDIAN_MCP_API_KEY
2. 启动本地 MCP
3. 启动 cloudflared 临时 HTTPS 通道
4. 输出涂鸦需要填写的 mcpServers JSON
```

停止本地调试：

```powershell
.\stop_tuya_debug.ps1
```

## 五、公网服务器部署

如果要让涂鸦平台直接调用新版 Agent，需要把本目录部署到当前公网 Ubuntu 服务器：

```text
/opt/guardian-agent
```

服务器上的两个服务保持不变：

```text
guardian-mcp.service
guardian-mcp-tunnel.service
```

部署后重启：

```bash
systemctl restart guardian-mcp
```

通常不需要重启 `guardian-mcp-tunnel.service`。只重启 MCP 服务时，临时 trycloudflare 公网地址一般不会变化。

## 六、已验证情况

本地已完成：

```text
python -m py_compile ...
python -m unittest discover -s tests -p test_guardian_tools.py -v
```

结果：

```text
9 个测试通过
语法检查通过
```

测试过程中有 sqlite 连接未关闭的 ResourceWarning，但不影响当前功能；后续可以作为代码质量优化项处理。
