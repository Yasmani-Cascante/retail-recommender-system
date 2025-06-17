# Script para reiniciar la aplicación con la configuración actualizada

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Verificar la configuración actual
Write-Host "Verificando configuración actual..." -ForegroundColor Green
python reset_client.py

# Detener procesos de Python (opcional)
Write-Host "`nDeteniendo procesos de Python activos..." -ForegroundColor Yellow
Get-Process -Name python* | Stop-Process -Force -ErrorAction SilentlyContinue

# Restablecer variables de entorno
Write-Host "`nRestableciendo variables de entorno..." -ForegroundColor Green
$env:GOOGLE_LOCATION = "global"
$env:GOOGLE_CATALOG = "default_catalog"
$env:GOOGLE_SERVING_CONFIG = "default_recommendation_config"

# Iniciar la aplicación
Write-Host "`nIniciando la aplicación..." -ForegroundColor Green
Write-Host "Presiona Ctrl+C para detener la aplicación"
python run.py
