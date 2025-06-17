# Script PowerShell para verificar la configuración específica default_recommendation_config

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Verificar específicamente la configuración default_recommendation_config en default_catalog
Write-Host "Verificando configuración específica 'default_recommendation_config' en el catálogo 'default_catalog'..." -ForegroundColor Green
python verify_retail_config_v2.py --config-id "default_recommendation_config" --catalog "default_catalog" --location "global"

Write-Host "`nVerificación completada." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
