<#
.SYNOPSIS
    Phase 8 Addendum 8.1: 查询服务状态

.DESCRIPTION
    - 读 scripts/logs/service.pid
    - PID 进程存活：调 GET /api/health 输出
      pid / uptime / status / scheduler jobs / collect_interval / db.size_mb / cache.hit_rate
    - 进程不在：输出"未运行"
    - ExitCode: 0 = 运行中, 1 = 停止

.EXAMPLE
    .\scripts\service\status.ps1
#>
$ErrorActionPreference = "Continue"

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDir = Join-Path $projectRoot "scripts\logs"
$pidFile = Join-Path $logDir "service.pid"

# 1. 读 PID
$pid = $null
if (Test-Path $pidFile) {
    $raw = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($raw -and ($raw -as [int])) {
        $candidate = [int]$raw
        if (Get-Process -Id $candidate -ErrorAction SilentlyContinue) {
            $pid = $candidate
        }
    }
}

if (-not $pid) {
    Write-Host "[status.ps1] 未运行（PID 文件不存在或进程已退出）" -ForegroundColor Yellow
    exit 1
}

# 2. 调 /api/health
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -ne 200) {
        Write-Host "[status.ps1] pid=$pid 存活但 /api/health 返回 HTTP $($r.StatusCode)" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "[status.ps1] pid=$pid 存活但 /api/health 不可达：$_" -ForegroundColor Yellow
    exit 1
}

$j = $r.Content | ConvertFrom-Json

# 3. collect_interval 从 env 读（API 不返回这个字段）
#    run.py 启动时 WORKERS/HOST/PORT 来自 env, HOTSPOT_COLLECT_INTERVAL_SECONDS
#    来自 pydantic-settings（env_prefix=HOTSPOT_）。从当前进程 env 读只能拿到
#    默认值，所以这里显示 config 默认 + env 覆盖的实际值
$collectInterval = $env:HOTSPOT_COLLECT_INTERVAL_SECONDS
if (-not $collectInterval) { $collectInterval = "300 (default)" }

# 4. 输出
Write-Host "pid: $pid"
Write-Host "uptime_s: $($j.uptime_s)"
Write-Host "status: $($j.status)"
Write-Host "version: $($j.version)"
Write-Host "scheduler.jobs: $($j.components.scheduler.jobs -join ', ')"
Write-Host "scheduler.ok: $($j.components.scheduler.ok)"
Write-Host "collect_interval_seconds: $collectInterval"
Write-Host "db.size_mb: $($j.components.db.size_mb)"
Write-Host "db.wal: $($j.components.db.wal.mode)"
Write-Host "db.integrity.ok: $($j.components.db.integrity.ok)"
Write-Host "cache.hit_rate.list: $($j.components.cache.hit_rate.list)"
Write-Host "cache.hit_rate.detail: $($j.components.cache.hit_rate.detail)"
Write-Host "cache.hit_rate.static: $($j.components.cache.hit_rate.static)"

exit 0
