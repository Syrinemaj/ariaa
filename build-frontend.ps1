# build-frontend.ps1
# Copie le source React dans le contexte Docker puis rebuild le container.
# Usage : .\build-frontend.ps1

$FRONTEND_SRC = "C:\Users\MSI\Downloads\web\frontend"
$ARIA_ROOT    = "D:\aria1.0\aria"
$FRONTEND_DST = "$ARIA_ROOT\frontend"

Write-Host "1/3  Copie des sources frontend..." -ForegroundColor Cyan
if (Test-Path $FRONTEND_DST) { Remove-Item $FRONTEND_DST -Recurse -Force }
Copy-Item $FRONTEND_SRC -Destination $FRONTEND_DST -Recurse -Exclude "node_modules","dist",".env*"

Write-Host "2/3  Rebuild du container aria-api..." -ForegroundColor Cyan
Set-Location $ARIA_ROOT
docker compose build api

Write-Host "3/3  Redemarrage du container..." -ForegroundColor Cyan
docker compose up -d api

Write-Host ""
Write-Host "OK  ARIA disponible sur http://localhost:8000" -ForegroundColor Green
