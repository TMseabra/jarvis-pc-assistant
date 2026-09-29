# Faz o serviço do Telegram do Jarvis arrancar com o Windows, em segundo plano (sem janela).
# Para desligar: apaga o atalho "Jarvis (Telegram)" da pasta shell:startup.
$root = Split-Path -Parent $PSScriptRoot
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Jarvis (Telegram).lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $root ".venv\Scripts\pythonw.exe"
$shortcut.Arguments = "-m jarvis.main --servico"
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Jarvis - controlo por Telegram"
$icon = Join-Path $root "assets\jarvis.ico"
if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
$shortcut.Save()

Write-Host "Atalho criado: $shortcutPath"
