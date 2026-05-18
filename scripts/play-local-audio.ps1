param(
  [Parameter(Mandatory = $true)]
  [string]$AudioPath,

  [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $AudioPath)) {
  throw "Audio file not found: $AudioPath"
}

$resolved = Resolve-Path -LiteralPath $AudioPath
$audioFile = $resolved.Path
$extension = [System.IO.Path]::GetExtension($audioFile)

if (-not ($extension -and $extension.Equals(".wav", [System.StringComparison]::OrdinalIgnoreCase))) {
  throw "Only WAV playback is supported by this script: $audioFile"
}

try {
  $player = New-Object System.Media.SoundPlayer $audioFile
  $player.Load()
  $player.PlaySync()

  Write-Output "PLAYBACK_CONFIRMED=1"
  Write-Output "PLAYBACK_BACKEND=SoundPlayer"
  Write-Output "PLAYSTATE_FINAL=WAV_SYNC_OK"
  exit 0
}
catch {
  throw ("SoundPlayer failed for WAV file '{0}': {1}" -f $audioFile, $_.Exception.Message)
}
