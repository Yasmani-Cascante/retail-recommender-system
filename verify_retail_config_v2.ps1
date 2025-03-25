# Script PowerShell actualizado para verificar la configuración de Google Cloud Retail API

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Verificar la versión de la biblioteca
Write-Host "Verificando la versión de google-cloud-retail y métodos disponibles..." -ForegroundColor Green
python check_retail_version.py

# Verificar la ubicación
$location = Read-Host -Prompt "`n¿Qué ubicación quieres usar? (Presiona Enter para usar 'us-central1')"
if ([string]::IsNullOrWhiteSpace($location)) {
    $location = "us-central1"
}

# Listar catálogos disponibles
Write-Host "`nListando catálogos disponibles..." -ForegroundColor Green
python verify_retail_config_v2.py --list-catalogs --location $location

# Verificar un catálogo específico
$catalog = Read-Host -Prompt "`n¿Qué catálogo quieres verificar? (Presiona Enter para usar 'retail_178362262166')"
if ([string]::IsNullOrWhiteSpace($catalog)) {
    $catalog = "retail_178362262166"
}

# Listar configuraciones del catálogo
Write-Host "`nListando configuraciones para el catálogo '$catalog'..." -ForegroundColor Green
python verify_retail_config_v2.py --list-configs --catalog $catalog --location $location

# Verificar configuración específica
$config = Read-Host -Prompt "`n¿Qué configuración quieres verificar? (Presiona Enter para usar 'default_recommendation_config')"
if ([string]::IsNullOrWhiteSpace($config)) {
    $config = "default_recommendation_config"
}

Write-Host "`nVerificando configuración específica '$config'..." -ForegroundColor Green
python verify_retail_config_v2.py --config-id $config --catalog $catalog --location $location

# Preguntar si se desea crear la configuración
$response = Read-Host -Prompt "`n¿Deseas crear la configuración si no existe? (S/N)"
if ($response -eq "S" -or $response -eq "s") {
    Write-Host "Intentando crear la configuración..." -ForegroundColor Green
    python verify_retail_config_v2.py --create --config-id $config --catalog $catalog --location $location
}

Write-Host "`nVerificación completada." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
