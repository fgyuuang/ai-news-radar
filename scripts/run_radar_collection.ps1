param(
    [string]$RuntimeRepo = (Join-Path (Split-Path -Parent $PSScriptRoot) '..\ai-news-radar-collection-runtime')
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
$mutex = [Threading.Mutex]::new($false, 'Global\PersonalRadarCollection')
$acquired = $false
try {
    try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { Write-Output 'Collection already active.'; exit 0 }
    $logDir = Join-Path $RuntimeRepo '.local-codex'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $log = Join-Path $logDir ('collection-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PATH = 'C:\Program Files\nodejs;C:\Users\fgy\AppData\Roaming\npm;D:\pro;' + $env:PATH
    & $python -X utf8 (Join-Path $PSScriptRoot 'radar_daily.py') collect --repo $RuntimeRepo *>> $log
    exit $LASTEXITCODE
} finally {
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
