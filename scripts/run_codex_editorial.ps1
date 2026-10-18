param(
    [string]$RuntimeRepo = (Join-Path (Split-Path -Parent $PSScriptRoot) '..\ai-news-radar-codex-runtime')
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw 'Project Python environment is missing.' }
if (-not (Test-Path -LiteralPath (Join-Path $RuntimeRepo '.git'))) { throw 'Dedicated runtime checkout is missing.' }
$taskLogDir = Join-Path $RuntimeRepo '.local-codex'
New-Item -ItemType Directory -Path $taskLogDir -Force | Out-Null
$taskLog = Join-Path $taskLogDir ('scheduled-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = 'C:\Program Files\nodejs;C:\Users\fgy\AppData\Roaming\npm;D:\pro;' + $env:PATH
& $taskPython -X utf8 (Join-Path $PSScriptRoot 'codex_editorial.py') --repo $RuntimeRepo --sync --publish *>> $taskLog
exit $LASTEXITCODE
