param(
    [int]$Port = 10001
)

# Get script directory (same as project root)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Locate local python3.11
$python = Join-Path $ScriptDir "python3.11\python.exe"

# Patch port in config.yaml
$configPath = Join-Path $ScriptDir "config.yaml"
$originalConfig = ""
if (Test-Path $configPath) {
    $originalConfig = Get-Content $configPath -Raw
    $patched = $originalConfig -replace "(?ms)(server:.*?\r?\n.*?port:\s*)(\d+)", "`${1}$Port"
    Set-Content $configPath -Value $patched -NoNewline -Encoding UTF8
}

# Start TougeIndexTTS service
try {
    & $python main.py
} finally {
    # Restore original config
    if ($originalConfig -ne "") {
        Set-Content $configPath -Value $originalConfig -NoNewline -Encoding UTF8
    }
}
