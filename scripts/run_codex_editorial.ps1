# Compatibility entry: Windows now collects only; AI runs in the native daily task.
param(
    [string]$RuntimeRepo = (Join-Path (Split-Path -Parent $PSScriptRoot) '..\ai-news-radar-collection-runtime')
)
& (Join-Path $PSScriptRoot 'run_radar_collection.ps1') -RuntimeRepo $RuntimeRepo
