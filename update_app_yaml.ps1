# Script PowerShell para actualizar app.yaml con la configuración de .env

# Leer la configuración actual de .env
$env_file = Get-Content -Path ".\.env" -Raw
$config_id = ""

# Extraer GOOGLE_SERVING_CONFIG
if ($env_file -match "GOOGLE_SERVING_CONFIG=(.*)") {
    $config_id = $matches[1].Trim()
    Write-Host "Configuración encontrada en .env: $config_id" -ForegroundColor Green
}
else {
    Write-Host "❌ No se pudo encontrar GOOGLE_SERVING_CONFIG en .env" -ForegroundColor Red
    Exit
}

# Actualizar app.yaml
$app_yaml = Get-Content -Path ".\app.yaml" -Raw
$updated_yaml = $app_yaml -replace "GOOGLE_SERVING_CONFIG: .*", "GOOGLE_SERVING_CONFIG: `"$config_id`""
Set-Content -Path ".\app.yaml" -Value $updated_yaml

# Actualizar script de despliegue
$deploy_script = Get-Content -Path ".\deploy_cloud_run.ps1" -Raw
$updated_deploy = $deploy_script -replace "GOOGLE_SERVING_CONFIG=.*?", "GOOGLE_SERVING_CONFIG=$config_id,"
Set-Content -Path ".\deploy_cloud_run.ps1" -Value $updated_deploy

Write-Host "✅ Configuración actualizada en todos los archivos." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
