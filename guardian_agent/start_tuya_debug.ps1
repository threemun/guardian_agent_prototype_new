$ErrorActionPreference = "Stop"

# This script starts both parts needed by Tuya:
# 1. Guardian MCP on this computer at http://127.0.0.1:8000/mcp
# 2. Cloudflare Tunnel, which gives that local endpoint a public HTTPS address
$root = $PSScriptRoot
$python = "C:\Users\MUN\.conda\envs\logistic_regression_implementation\python.exe"
$cloudflared = Join-Path $root "tools\cloudflared.exe"
$secretFile = Join-Path $root ".env.tuya.local"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}
if (-not (Test-Path -LiteralPath $cloudflared)) {
    throw "cloudflared not found: $cloudflared"
}
if (-not (Test-Path -LiteralPath $secretFile)) {
    throw "Local secret file not found: $secretFile"
}

$secretLine = Get-Content -LiteralPath $secretFile |
    Where-Object { $_ -match '^GUARDIAN_MCP_API_KEY=' } |
    Select-Object -First 1
$apiKey = ($secretLine -split '=', 2)[1].Trim()
if (-not $apiKey) {
    throw "GUARDIAN_MCP_API_KEY is empty in .env.tuya.local"
}

# Stop only processes previously started by this project.
& (Join-Path $root "stop_tuya_debug.ps1") -Quiet

$serverOut = Join-Path $root "guardian-mcp.stdout.log"
$serverErr = Join-Path $root "guardian-mcp.stderr.log"
$tunnelOut = Join-Path $root "cloudflared.stdout.log"
$tunnelErr = Join-Path $root "cloudflared.stderr.log"
Remove-Item -LiteralPath $serverOut, $serverErr, $tunnelOut, $tunnelErr -Force -ErrorAction SilentlyContinue

$env:GUARDIAN_MCP_API_KEY = $apiKey
$env:GUARDIAN_MCP_HOST = "127.0.0.1"
$env:GUARDIAN_MCP_PORT = "8000"
$server = Start-Process -FilePath $python `
    -ArgumentList "mcp_server.py" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $serverOut `
    -RedirectStandardError $serverErr `
    -PassThru
Set-Content -LiteralPath (Join-Path $root ".guardian-mcp.pid") -Value $server.Id

# Give the local server up to 15 seconds to bind port 8000.
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect("127.0.0.1", 8000)
        $client.Dispose()
        $ready = $true
        break
    } catch {
        if ($server.HasExited) {
            throw "Guardian MCP failed to start. See guardian-mcp.stderr.log"
        }
    }
}
if (-not $ready) {
    throw "Guardian MCP did not open port 8000 in time."
}

# HTTP/2 works more reliably than QUIC on networks that block UDP traffic.
$tunnel = Start-Process -FilePath $cloudflared `
    -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000", "--protocol", "http2", "--no-autoupdate" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $tunnelOut `
    -RedirectStandardError $tunnelErr `
    -PassThru
Set-Content -LiteralPath (Join-Path $root ".cloudflared.pid") -Value $tunnel.Id

# Quick Tunnels print their temporary public hostname to the error log.
$publicBaseUrl = $null
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    Start-Sleep -Seconds 1
    if (Test-Path -LiteralPath $tunnelErr) {
        $log = Get-Content -LiteralPath $tunnelErr -Raw
        $match = [regex]::Match($log, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) {
            $publicBaseUrl = $match.Value
            break
        }
    }
    if ($tunnel.HasExited) {
        throw "Cloudflare Tunnel failed to start. See cloudflared.stderr.log"
    }
}
if (-not $publicBaseUrl) {
    throw "Cloudflare did not return a public URL within 90 seconds."
}

$mcpUrl = "$publicBaseUrl/mcp"
Set-Content -LiteralPath (Join-Path $root ".tuya-mcp-url.txt") -Value $mcpUrl

Write-Host ""
Write-Host "Guardian MCP is ready for Tuya." -ForegroundColor Green
Write-Host "MCP URL: $mcpUrl"
Write-Host "Header name: Authorization"
Write-Host "Header value: Bearer $apiKey"
Write-Host ""
Write-Host "Keep this computer online. Run .\stop_tuya_debug.ps1 to stop access."
