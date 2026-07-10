<#
.SYNOPSIS
    Phase 8 Addendum 8.1: 后台启动后端服务（不阻塞当前 shell）

.DESCRIPTION
    - WORKERS=4, HOST=0.0.0.0, PORT=8000
    - 日志写到 scripts/logs/service.out.log
    - PID 写到 scripts/logs/service.pid
    - 启动后 5s 调 GET /api/health 验证就绪（最多 30s）
    - 用 Start-Process -WindowStyle Hidden 不阻塞当前 shell

.EXAMPLE
    .\scripts\service\start.ps1
#>
$ErrorActionPreference = "Stop"

# 项目根目录: .../hotspot-map
# $PSScriptRoot = .../hotspot-map/scripts/service
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# 日志目录
$logDir = Join-Path $projectRoot "scripts\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

# 端口占用检查
$portInUse = netstat -ano | findstr :8000
if ($portInUse) {
    Write-Host "[start.ps1] 端口 8000 已被占用：$portInUse" -ForegroundColor Red
    Write-Host "[start.ps1] 请先运行 .\scripts\service\stop.ps1 或手动 Stop-Process" -ForegroundColor Yellow
    exit 1
}

# PID 文件路径
$pidFile = Join-Path $logDir "service.pid"
if (Test-Path $pidFile) {
    $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "[start.ps1] 旧 PID $oldPid 仍在运行，请先 stop.ps1" -ForegroundColor Red
        exit 1
    } else {
        Remove-Item $pidFile -Force
    }
}

# 启动参数
$logPath = Join-Path $logDir "service.out.log"
$env:HOST = "0.0.0.0"
$env:PORT = "8000"
$env:WORKERS = "4"

Write-Host "[start.ps1] 启动后端: WORKERS=4 HOST=0.0.0.0 PORT=8000" -ForegroundColor Cyan
Write-Host "[start.ps1] cwd: $projectRoot" -ForegroundColor Cyan
Write-Host "[start.ps1] log: $logPath" -ForegroundColor Cyan

# 后台启动（不阻塞当前 shell）
$proc = Start-Process -FilePath "python" `
    -ArgumentList "run.py" `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError "$logPath.err" `
    -PassThru -WindowStyle Hidden

# 写入 PID
Set-Content -Path $pidFile -Value $proc.Id -NoNewline
Write-Host "[start.ps1] 已启动 pid=$($proc.Id) / log=$logPath" -ForegroundColor Green

# 启动后 5s 等待，然后调 /api/health 验证（最多 30s）
Start-Sleep -Seconds 5
$ready = $false
for ($i = 0; $i -lt 6; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 5
    }
}

if ($ready) {
    Write-Host "[start.ps1] /api/health ready [OK]" -ForegroundColor Green
} else {
    Write-Host "[start.ps1] warn: /api/health not ready in 30s, check $logPath.err" -ForegroundColor Yellow
}
