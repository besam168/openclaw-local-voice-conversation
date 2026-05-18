param(
  [string]$Config,

  [string]$Python = "python",

  [string]$Text,

  [switch]$NoPlay,

  [switch]$ListDevices
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $repoRoot) {
  $repoRoot = (Get-Location).Path
}
$repoRoot = (Resolve-Path -LiteralPath $repoRoot).Path

if (-not $Config -or [string]::IsNullOrWhiteSpace($Config)) {
  $localConfig = Join-Path $repoRoot "config.json"
  if (Test-Path -LiteralPath $localConfig) {
    $Config = $localConfig
  }
  else {
    $Config = Join-Path $repoRoot "config.example.json"
  }
}

if (-not [System.IO.Path]::IsPathRooted($Config)) {
  $Config = Join-Path $repoRoot $Config
}
$Config = (Resolve-Path -LiteralPath $Config).Path

$voiceChatPy = Join-Path $repoRoot "scripts\voice_chat.py"
if (-not (Test-Path -LiteralPath $voiceChatPy)) {
  throw "Cannot find scripts/voice_chat.py at: $voiceChatPy"
}

$argsList = @($voiceChatPy, "--config", $Config)
if ($Text -and -not [string]::IsNullOrWhiteSpace($Text)) {
  $argsList += @("--text", $Text)
}
if ($NoPlay) {
  $argsList += "--no-play"
}
if ($ListDevices) {
  $argsList += "--list-devices"
}

& $Python @argsList
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
  exit $exitCode
}
