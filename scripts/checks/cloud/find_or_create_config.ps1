# Script PowerShell para encontrar configuraciones existentes o crear una básica

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Listar todas las configuraciones existentes
Write-Host "Listando todas las configuraciones existentes en el catálogo 'default_catalog'..." -ForegroundColor Green
python verify_retail_config_v2.py --list-configs --catalog "default_catalog" --location "global"

# Preguntar qué configuración usar
Write-Host "`n¿Qué configuración deseas usar? (deja en blanco para crear una nueva)" -ForegroundColor Cyan
$config_id = Read-Host

if ([string]::IsNullOrWhiteSpace($config_id)) {
    # Crear una configuración simple
    Write-Host "Creando una configuración simple..." -ForegroundColor Green
    python create_simple_config.py
    $config_id = "default_search_config"
}

# Actualizar el archivo .env con la configuración seleccionada
Write-Host "`nActualizando archivo .env con la configuración seleccionada..." -ForegroundColor Green
$env_file = Get-Content -Path ".\.env" -Raw
$updated_env = $env_file -replace "GOOGLE_SERVING_CONFIG=.*", "GOOGLE_SERVING_CONFIG=$config_id"
Set-Content -Path ".\.env" -Value $updated_env

# Mostrar la configuración final
Write-Host "`nConfiguración actualizada:" -ForegroundColor Green
Get-Content ".\.env" | Select-String "GOOGLE_"

Write-Host "`nConfiguración completada. Ahora puedes ejecutar tu aplicación." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
