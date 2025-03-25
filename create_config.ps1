# Script PowerShell para crear la configuración de servicio

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Crear la configuración
Write-Host "Creando configuración 'default_recommendation_config' en el catálogo 'default_catalog'..." -ForegroundColor Green
python create_config.py

Write-Host "`nVerificar si la configuración fue creada..." -ForegroundColor Green
python verify_retail_config_v2.py --config-id "default_recommendation_config" --catalog "default_catalog" --location "global"

Write-Host "`nConfiguración completada." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
