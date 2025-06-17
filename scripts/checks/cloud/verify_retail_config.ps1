# Script PowerShell para verificar la configuración de Google Cloud Retail API

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Ejecutar el script Python
Write-Host "Verificando configuración de catálogo..." -ForegroundColor Green
python verify_retail_config.py --list-configs

Write-Host "`nVerificando configuración específica..." -ForegroundColor Green
python verify_retail_config.py --config-id "default_recommendation_config"

# Preguntar si se desea crear la configuración en caso de que no exista
Write-Host "`n¿Deseas crear la configuración si no existe? (S/N)" -ForegroundColor Cyan
$response = Read-Host
if ($response -eq "S" -or $response -eq "s") {
    Write-Host "Intentando crear la configuración..." -ForegroundColor Green
    python verify_retail_config.py --create
}

Write-Host "`nVerificación completada." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
