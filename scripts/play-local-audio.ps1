param(
  [Parameter(Mandatory = $true)]
  [string]$AudioPath,

  [int]$TimeoutSeconds = 60,

  [ValidateSet("auto", "soundplayer", "mci")]
  [string]$Backend = "auto"
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

$fileInfo = Get-Item -LiteralPath $audioFile
Write-Output ("PLAYBACK_FILE={0}" -f $audioFile)
Write-Output ("PLAYBACK_FILE_BYTES={0}" -f $fileInfo.Length)
Write-Output ("PLAYBACK_BACKEND_REQUESTED={0}" -f $Backend)

function Invoke-SoundPlayerPlayback {
  param([string]$Path)

  $player = New-Object System.Media.SoundPlayer $Path
  $player.Load()
  $player.PlaySync()

  Write-Output "PLAYBACK_BACKEND=SoundPlayer"
  Write-Output "PLAYSTATE_FINAL=WAV_SYNC_OK"
}

function Invoke-MciPlayback {
  param([string]$Path)

  if (-not ("WinmmNative" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class WinmmNative {
  [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
  public static extern int mciSendString(string command, StringBuilder returnValue, int returnLength, IntPtr winHandle);
}
"@
  }

  $alias = "openclawVoice" + ([Guid]::NewGuid().ToString("N"))
  $quotedPath = '"' + $Path.Replace('"', '""') + '"'

  try {
    $openResult = [WinmmNative]::mciSendString("open $quotedPath type waveaudio alias $alias", $null, 0, [IntPtr]::Zero)
    if ($openResult -ne 0) {
      throw "mci open failed with code $openResult"
    }

    $playResult = [WinmmNative]::mciSendString("play $alias wait", $null, 0, [IntPtr]::Zero)
    if ($playResult -ne 0) {
      throw "mci play failed with code $playResult"
    }

    Write-Output "PLAYBACK_BACKEND=MCI"
    Write-Output "PLAYSTATE_FINAL=WAV_SYNC_OK"
  }
  finally {
    [void][WinmmNative]::mciSendString("close $alias", $null, 0, [IntPtr]::Zero)
  }
}

try {
  if ($Backend -eq "mci") {
    Invoke-MciPlayback -Path $audioFile
  }
  else {
    Invoke-SoundPlayerPlayback -Path $audioFile
  }

  Write-Output "PLAYBACK_CONFIRMED=1"
  Write-Output "PLAYBACK_NOTE=The Windows API reported successful playback. If you still hear nothing, check the default output device, mixer volume, mute state, or try backend=mci in config.json."
  exit 0
}
catch {
  if ($Backend -eq "auto") {
    Write-Output ("PLAYBACK_FALLBACK_REASON={0}" -f $_.Exception.Message)
    Invoke-MciPlayback -Path $audioFile
    Write-Output "PLAYBACK_CONFIRMED=1"
    Write-Output "PLAYBACK_NOTE=SoundPlayer failed, MCI fallback reported successful playback."
    exit 0
  }

  throw ("Playback failed for WAV file '{0}' with backend '{1}': {2}" -f $audioFile, $Backend, $_.Exception.Message)
}
