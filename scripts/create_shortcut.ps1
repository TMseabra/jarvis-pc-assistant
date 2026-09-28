# Cria o atalho "Jarvis" no ambiente de trabalho (duplo clique abre o Jarvis num terminal).
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Jarvis.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $root "Jarvis.bat"
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Jarvis - assistente pessoal do PC"
$icon = Join-Path $root "assets\jarvis.ico"
if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
$shortcut.Save()

Write-Host "Atalho criado: $shortcutPath"
