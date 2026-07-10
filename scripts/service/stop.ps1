<#
.SYNOPSIS
    Phase 8 Addendum 8.1: 优雅停止后端服务（10s 超时）

.DESCRIPTION
    - 优先读 scripts/logs/service.pid
    - 没有 PID 文件时：Get-Process python | Where-Object 命令行匹配 run.py
    - 第一次尝试：调 /api/health → 健康则 Stop-Process -Force
    - Windows 上 SIGTERM = SIGKILL (Stop-Process -Force)
    - 10s 超时（Phase 8.1.1 stop() 容错后端保证 10s 内必退）
    - 输出：stopped pid=XXXX rc=...

.EXAMPLE
    .\scripts\service\stop.ps1
#>
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDir = Join-Path $projectRoot "scripts\logs"
$pidFile = Join-Path $logDir "service.pid"

# 1. 取 PID
$pid = $null
if (Test-Path $pidFile) {
    $raw = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($raw -and ($raw -as [int]) -and (Get-Process -Id ([int]$raw) -ErrorAction SilentlyContinue)) {
        $pid = [int]$raw
    } else {
        Write-Host "[stop.ps1] PID file expired, cleaning up" -ForegroundColor Yellow
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

# 2. 没有 PID 时按命令行匹配 run.py
if (-not $pid) {
    $candidates = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
            $cmd -and $cmd -match "run\.py"
        } catch { $false }
    }
    if ($candidates) {
        $pid = $candidates[0].Id
        Write-Host "[stop.ps1] found pid=$pid by cmdline match" -ForegroundColor Cyan
    } else {
        Write-Host "[stop.ps1] no running service found" -ForegroundColor Yellow
        exit 1
    }
}

# 3. 第一次尝试：调 /api/health → 健康就 Stop-Process
$healthy = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        $healthy = $true
    }
} catch {
    $healthy = $false
}

if ($healthy) {
    Write-Host "[stop.ps1] /api/health 200, directly Stop-Process pid=$pid" -ForegroundColor Cyan
} else {
    Write-Host "[stop.ps1] /api/health unreachable, still Stop-Process pid=$pid" -ForegroundColor Yellow
}

# 4. Windows 下 Stop-Process -Force = 硬杀（无 SIGTERM 概念）
# Phase 8.1.1 stop() 容错保证 10s 内必退
try {
    $proc = Stop-Process -Id $pid -Force -PassThru -ErrorAction Stop
    # 等待退出（已退出则立即返回）
    $proc.WaitForExit(10000) | Out-Null
    $rc = $proc.ExitCode
    Write-Host "stopped pid=$pid rc=$rc" -ForegroundColor Green
} catch {
    Write-Host "[stop.ps1] Stop-Process failed" -ForegroundColor Red
    if (-not (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
        Write-Host "stopped pid=$pid rc=0" -ForegroundColor Green
    } else {
        exit 1
    }
}

# 5. 清理 PID 文件
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

# 6. 验证端口释放（最多 5s）
$portFree = $false
for ($i = 0; $i -lt 5; $i++) {
    $portInUse = netstat -ano | findstr :8000
    if (-not $portInUse) {
        $portFree = $true
        break
    }
    Start-Sleep -Seconds 1
}
if ($portFree) {
    Write-Host "[stop.ps1] port 8000 released [OK]" -ForegroundColor Green
} else {
    Write-Host "[stop.ps1] warn: port 8000 still in use" -ForegroundColor Yellow
}
