param(
    [int]$Port = 10001
)

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Locate python
$python = Join-Path $ScriptDir "python3.11\python.exe"
$mainPy = Join-Path $ScriptDir "main.py"

# Patch config.yaml
$configPath = Join-Path $ScriptDir "config.yaml"
$originalConfig = ""
if (Test-Path $configPath) {
    $originalConfig = Get-Content $configPath -Raw
    $patched = $originalConfig -replace "(?ms)(server:.*?\r?\n.*?port:\s*)(\d+)", "`${1}$Port"
    Set-Content $configPath -Value $patched -NoNewline -Encoding UTF8
}

# Start service
try {
    & $python $mainPy
} finally {
    if ($originalConfig -ne "") {
        Set-Content $configPath -Value $originalConfig -NoNewline -Encoding UTF8
    }
}
