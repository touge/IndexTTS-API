# ===============================
# Copy indextts directory from GitHub to vendor/
# Author: Long's Copilot
# ===============================

$repoUrl = "https://github.com/index-tts/index-tts/archive/refs/heads/main.zip"
$tempZip = "$env:TEMP\index-tts.zip"
$tempDir = "$env:TEMP\index-tts-main"
$targetDir = "vendor\indextts"

Write-Host "Downloading index-tts repository..."
Invoke-WebRequest -Uri $repoUrl -OutFile $tempZip -UseBasicParsing

Write-Host "Extracting..."
Expand-Archive -Path $tempZip -DestinationPath $env:TEMP -Force

# Ensure vendor directory exists
if (!(Test-Path "vendor")) {
    New-Item -ItemType Directory -Path "vendor" | Out-Null
}

# Remove old directory if exists
if (Test-Path $targetDir) {
    Write-Host "Removing old vendor/indextts..."
    Remove-Item -Recurse -Force $targetDir
}

# Copy new directory
Write-Host "Copying indextts to vendor..."
Copy-Item -Recurse -Force "$tempDir\indextts" $targetDir

# Cleanup
Write-Host "Cleaning up..."
Remove-Item $tempZip -Force
Remove-Item $tempDir -Recurse -Force

Write-Host "Done! indextts has been copied to vendor/indextts"
