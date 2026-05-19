param(
  [string]$Config = "$PSScriptRoot\config.json"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot
python -m app.main --config $Config
