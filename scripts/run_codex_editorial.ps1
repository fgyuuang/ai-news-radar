param(
    [string]$RuntimeRepo = (Join-Path (Split-Path -Parent $PSScriptRoot) '..\ai-news-radar-codex-runtime')
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskShell = Join-Path $PSHOME 'pwsh.exe'
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw 'Project Python environment is missing.' }
if (-not (Test-Path -LiteralPath $taskShell -PathType Leaf)) { throw 'PowerShell 7 executable is missing.' }
if (-not (Test-Path -LiteralPath (Join-Path $RuntimeRepo '.git'))) { throw 'Dedicated runtime checkout is missing.' }
$taskLogDir = Join-Path $RuntimeRepo '.local-codex'
New-Item -ItemType Directory -Path $taskLogDir -Force | Out-Null
$taskLog = Join-Path $taskLogDir ('scheduled-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = 'C:\Program Files\nodejs;C:\Users\fgy\AppData\Roaming\npm;D:\pro;' + $env:PATH
& $taskPython -X utf8 (Join-Path $PSScriptRoot 'codex_editorial.py') --repo $RuntimeRepo --sync --publish *>> $taskLog
$editorialExit = $LASTEXITCODE
$combinedExit = $editorialExit

# The legacy digest owns the user-requested Obsidian archive and QQ/WeChat
# delivery path. Run it once per China calendar date, at or after 09:00, after
# checking its established daily status and channel receipts. A local claim
# also prevents retries after an interrupted or uncertain send.
$shanghaiNow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::Now, 'China Standard Time')
if ($shanghaiNow.Hour -ge 9) {
    $dateKey = $shanghaiNow.ToString('yyyyMMdd')
    $digestRoot = Split-Path -Parent $taskRoot
    $digestReports = Join-Path $digestRoot 'reports\math-digest'
    $dailyStatus = Join-Path $digestReports "daily-status-$dateKey.log"
    $deliveryLogs = @(Get-ChildItem -LiteralPath $digestReports -Filter "delivery-$dateKey-*.log" -File -ErrorAction SilentlyContinue)
    $claim = Join-Path $taskLogDir "math-digest-started-$dateKey.log"
    if ((Test-Path -LiteralPath $dailyStatus) -or $deliveryLogs.Count -gt 0) {
        Add-Content -LiteralPath $taskLog -Value "Math digest skipped: a daily status or delivery record already exists for $dateKey."
    } elseif (Test-Path -LiteralPath $claim) {
        Add-Content -LiteralPath $taskLog -Value "Math digest skipped: the daily run was already claimed for $dateKey."
    } else {
        $claimStream = $null
        try {
            $claimStream = [System.IO.File]::Open($claim, [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            $claimText = "claimed_at=$($shanghaiNow.ToString('o')); date=$dateKey" + [Environment]::NewLine
            $claimBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($claimText)
            $claimStream.Write($claimBytes, 0, $claimBytes.Length)
            Add-Content -LiteralPath $taskLog -Value "Starting the once-daily math digest for $dateKey."
            $digestScript = Join-Path $digestRoot 'scripts\codex_math_digest.ps1'
            & $taskShell -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File $digestScript *>> $taskLog
            $digestExit = $LASTEXITCODE
            Add-Content -LiteralPath $taskLog -Value "Math digest process exit code: $digestExit."
            if ($digestExit -ne 0) { $combinedExit = 1 }
        } catch {
            Add-Content -LiteralPath $taskLog -Value "Math digest dispatcher failed: $($_.Exception.GetType().Name)."
            $combinedExit = 1
        } finally {
            if ($null -ne $claimStream) { $claimStream.Dispose() }
        }
    }
}

exit $combinedExit
