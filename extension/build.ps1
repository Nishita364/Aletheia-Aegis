# Build script for the browser extension (Windows PowerShell).
# Usage:
#   .\build.ps1            — uses manifest.json (MV3, Chrome 114+)
#   .\build.ps1 --firefox  — uses manifest.v2.json (MV2, Firefox 115+)

param(
    [switch]$firefox
)

$ErrorActionPreference = "Stop"

if ($firefox) {
    $target = "firefox"
    $distDir = "dist\firefox"
} else {
    $target = "chrome"
    $distDir = "dist\chrome"
}

# Create output directory
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

# Copy common files
Copy-Item -Path "background.js", "content.js", "popup.html", "popup.js" -Destination $distDir
Copy-Item -Path "icons" -Destination $distDir -Recurse -Force

# Copy the correct manifest
if ($firefox) {
    Copy-Item -Path "manifest.v2.json" -Destination "$distDir\manifest.json" -Force
    Write-Host "Built Firefox (MV2) extension -> $distDir\"
} else {
    Copy-Item -Path "manifest.json" -Destination "$distDir\manifest.json" -Force
    Write-Host "Built Chrome (MV3) extension -> $distDir\"
}
