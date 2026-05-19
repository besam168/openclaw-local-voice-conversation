$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut('C:\Users\besam\Desktop\OpenClaw本地语音对话.lnk')
$s.TargetPath = 'C:\Users\besam\.openclaw\workspace\openclaw-local-voice-conversation\启动本地语音对话.bat'
$s.WorkingDirectory = 'C:\Users\besam\.openclaw\workspace\openclaw-local-voice-conversation'
$s.IconLocation = 'C:\Windows\System32\SHELL32.dll,220'
$s.Save()
