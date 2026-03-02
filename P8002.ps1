<#
.SYNOPSIS
    IndexTTS API Startup Script

.DESCRIPTION
    Auto-activate python3.11 conda environment and start IndexTTS API service
    Support custom IP address and port

.PARAMETER HostAddress
    Service listening IP address, default is 0.0.0.0

.PARAMETER Port
    Service listening port, default is 8002

.EXAMPLE
    .\start.ps1
    Start with default config (0.0.0.0:8002)

.EXAMPLE
    .\start.ps1 -Port 9000
    Start with port 9000

.EXAMPLE
    .\start.ps1 -HostAddress 127.0.0.1 -Port 9000
    Start with 127.0.0.1:9000
#>

param(
    [string]$HostAddress = "",
    [int]$Port = 8002
)

# Set console encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  IndexTTS API Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if local python3.11 directory exists
$localPythonDir = Join-Path $ScriptDir "python3.11"
$usePythonCmd = "python"

if (Test-Path $localPythonDir) {
    Write-Host "[INFO] Found local Python environment: $localPythonDir" -ForegroundColor Green
    $pythonExe = Join-Path $localPythonDir "python.exe"
    
    if (Test-Path $pythonExe) {
        Write-Host "[INFO] Using local Python: $pythonExe" -ForegroundColor Green
        $usePythonCmd = $pythonExe
    } else {
        Write-Host "[WARNING] python.exe not found in local environment, trying conda..." -ForegroundColor Yellow
        
        # Fallback to conda
        $condaPath = (Get-Command conda -ErrorAction SilentlyContinue).Source
        if (-not $condaPath) {
            Write-Host "[ERROR] Neither local Python nor conda found" -ForegroundColor Red
            pause
            exit 1
        }
        
        Write-Host "[INFO] Activating conda environment: python3.11 ..." -ForegroundColor Yellow
        conda activate python3.11
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to activate conda environment" -ForegroundColor Red
            pause
            exit 1
        }
        Write-Host "[SUCCESS] Conda environment activated" -ForegroundColor Green
    }
} else {
    Write-Host "[INFO] Local python3.11 directory not found, using conda..." -ForegroundColor Yellow
    
    # Check if conda is available
    $condaPath = (Get-Command conda -ErrorAction SilentlyContinue).Source
    if (-not $condaPath) {
        Write-Host "[ERROR] conda command not found" -ForegroundColor Red
        pause
        exit 1
    }
    
    Write-Host "[INFO] Activating conda environment: python3.11 ..." -ForegroundColor Yellow
    conda activate python3.11
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to activate conda environment" -ForegroundColor Red
        pause
        exit 1
    }
    Write-Host "[SUCCESS] Conda environment activated" -ForegroundColor Green
}

Write-Host ""

# Check if main.py exists
if (-not (Test-Path "main.py")) {
    Write-Host "[ERROR] main.py not found, please ensure you are running this script in the correct directory" -ForegroundColor Red
    pause
    exit 1
}

# Build startup command
# $pythonCmd = "$usePythonCmd main.py"
$pythonCmd = "$usePythonCmd main.py --task TTSGenerator"


# If Host or Port is specified, temporarily modify config.yaml
$configModified = $false
$originalConfig = ""

if ($HostAddress -ne "" -or $Port -ne 0) {
    Write-Host "[INFO] Custom parameters detected, updating config..." -ForegroundColor Yellow
    
    if (Test-Path "config.yaml") {
        # Backup original config
        $originalConfig = Get-Content "config.yaml" -Raw
        
        # Read config file
        $config = Get-Content "config.yaml" -Raw
        
        # Update Host in server section
        if ($HostAddress -ne "") {
            # Match: server:\n  host: xxx
            $config = $config -replace "(?ms)(server:\s*\r?\n\s*host:\s*)([^\r\n]+)", "`${1}$HostAddress"
            Write-Host "  - Set Host: $HostAddress" -ForegroundColor Cyan
        }
        
        # Update Port in server section
        if ($Port -ne 0) {
            # Match: server:\n  ...  port: xxx
            $config = $config -replace "(?ms)(server:.*?\r?\n.*?port:\s*)(\d+)", "`${1}$Port"
            Write-Host "  - Set Port: $Port" -ForegroundColor Cyan
        }
        
        # Write back to config file
        Set-Content "config.yaml" -Value $config -NoNewline -Encoding UTF8
        $configModified = $true
    } else {
        Write-Host "[WARNING] config.yaml not found, will use default config" -ForegroundColor Yellow
    }
}


Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting service..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start service
try {
    Invoke-Expression $pythonCmd
} catch {
    Write-Host ""
    Write-Host "[ERROR] Service startup failed: $_" -ForegroundColor Red
} finally {
    # Restore original config
    if ($configModified -and $originalConfig -ne "") {
        Write-Host ""
        Write-Host "[INFO] Restoring original config..." -ForegroundColor Yellow
        Set-Content "config.yaml" -Value $originalConfig -NoNewline
        Write-Host "[SUCCESS] Config restored" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Service stopped" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}
