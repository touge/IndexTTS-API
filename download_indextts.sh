#!/bin/bash
# ===============================
# Copy indextts directory from GitHub to vendor/
# Author: Long's Copilot
# ===============================

repoUrl="https://github.com/index-tts/index-tts/archive/refs/heads/main.zip"
tempZip="/tmp/index-tts.zip"
tempDir="/tmp/index-tts-main"
targetDir="vendor/indextts"

echo "Downloading index-tts repository..."
curl -L -o "$tempZip" "$repoUrl"

echo "Extracting..."
unzip -o "$tempZip" -d /tmp

# Ensure vendor directory exists
if [ ! -d "vendor" ]; then
    mkdir -p "vendor"
fi

# Remove old directory if exists
if [ -d "$targetDir" ]; then
    echo "Removing old vendor/indextts..."
    rm -rf "$targetDir"
fi

# Copy new directory
echo "Copying indextts to vendor..."
cp -rf "$tempDir/indextts" "$targetDir"

# Cleanup
echo "Cleaning up..."
rm -f "$tempZip"
rm -rf "$tempDir"

echo "Done! indextts has been copied to vendor/indextts"