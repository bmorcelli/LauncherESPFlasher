# Run from anywhere — uses absolute path of this script's parent.
# Requires Docker Desktop or Rancher Desktop with linux/arm64 support.

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Building LauncherESPFlasher .deb package..."
Write-Host "Project root: $ProjectRoot"
Write-Host ""

docker run --rm `
    --platform linux/arm64 `
    -v "${ProjectRoot}:/src" `
    -w /src `
    ghcr.io/cardputerzero/build-env:latest `
    bash scripts/pack-deb.sh

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed (exit code $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Package ready in dist/:"
Get-ChildItem "$ProjectRoot\dist\*.deb" | Format-Table Name, Length, LastWriteTime
