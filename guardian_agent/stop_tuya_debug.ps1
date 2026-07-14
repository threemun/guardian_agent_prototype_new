param([switch]$Quiet)

$root = $PSScriptRoot
$pidFiles = @(
    (Join-Path $root ".cloudflared.pid"),
    (Join-Path $root ".guardian-mcp.pid")
)

foreach ($pidFile in $pidFiles) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        continue
    }

    $savedPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
    if ($savedPid -match '^\d+$') {
        Stop-Process -Id ([int]$savedPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

if (-not $Quiet) {
    Write-Host "Guardian MCP and Cloudflare Tunnel have been stopped."
}
