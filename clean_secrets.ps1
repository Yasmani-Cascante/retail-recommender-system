# PowerShell script para limpiar secretos del historial de Git

Write-Host "⚠️ ADVERTENCIA: Este script modificará el historial de Git" -ForegroundColor Red
Write-Host "⚠️ Solo utilízalo en repositorios donde puedas reescribir la historia" -ForegroundColor Red
Write-Host "⚠️ Se requiere hacer force push después de ejecutar este script" -ForegroundColor Red
Write-Host ""
Write-Host "Este script reemplazará las claves de API y tokens en archivos de scripts de despliegue." -ForegroundColor Yellow
Write-Host "Asegúrate de haber creado y configurado el archivo .env.secrets antes de continuar." -ForegroundColor Yellow
Write-Host ""

$Confirmation = Read-Host "¿Deseas continuar? (S/N)"
if ($Confirmation -ne "S") {
    Write-Host "Operación cancelada por el usuario." -ForegroundColor Yellow
    exit 0
}

# Patrón para buscar y reemplazar
$ShopifyTokenPattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
$ApiKeyPattern = "API_KEY=[a-zA-Z0-9]+"

# Archivos a procesar
$FilesToProcess = @(
    "deploy_tfidf_events_final.ps1",
    "deploy_tfidf_full_metrics.ps1",
    "deploy_tfidf_shopify.ps1",
    "deploy_tfidf_shopify.py",
    "deploy_tfidf_shopify_improved.ps1",
    "deploy_prediction_fix.ps1"
)

# 1. Crear un archivo temporal con los reemplazos
Write-Host "Generando script para BFG Repo-Cleaner..." -ForegroundColor Yellow

$ReplacementContent = @"
SHOPIFY_ACCESS_TOKEN=***REMOVED***
API_KEY=***REMOVED***
"@

$ReplacementContent | Out-File -FilePath "replacements.txt" -Encoding utf8

# 2. Instrucciones para el usuario
Write-Host "`nPara limpiar los secretos del historial de Git, sigue estos pasos:" -ForegroundColor Cyan
Write-Host "1. Descarga BFG Repo-Cleaner desde: https://rtyley.github.io/bfg-repo-cleaner/" -ForegroundColor White
Write-Host "2. Coloca el archivo JAR descargado en este directorio" -ForegroundColor White
Write-Host "3. Ejecuta los siguientes comandos:" -ForegroundColor White
Write-Host "`n   git clone --mirror https://github.com/Yasmani-Cascante/retail-recommender-system.git repo-mirror.git" -ForegroundColor Gray
Write-Host "   java -jar bfg-1.14.0.jar --replace-text replacements.txt repo-mirror.git" -ForegroundColor Gray
Write-Host "   cd repo-mirror.git" -ForegroundColor Gray
Write-Host "   git reflog expire --expire=now --all" -ForegroundColor Gray
Write-Host "   git gc --prune=now --aggressive" -ForegroundColor Gray
Write-Host "   git push" -ForegroundColor Gray
Write-Host "`n4. Luego, actualiza tu repositorio local:" -ForegroundColor White
Write-Host "   cd .." -ForegroundColor Gray
Write-Host "   git pull origin" -ForegroundColor Gray

# 3. Como medida inmediata, actualizar los archivos localmente
Write-Host "`nActualizando archivos localmente para futuros commits..." -ForegroundColor Yellow

# Cargar la configuración de secretos
. .\deploy_common.ps1
$SecretsLoaded = Load-SecretVariables
if (-not $SecretsLoaded) {
    Write-Host "Error: No se pudieron cargar las variables secretas." -ForegroundColor Red
    exit 1
}

foreach ($File in $FilesToProcess) {
    if (Test-Path $File) {
        Write-Host "Procesando archivo: $File" -ForegroundColor Cyan
        
        # Leer contenido
        $Content = Get-Content $File -Raw
        
        # Reemplazar patrones
        $Content = $Content -replace $ShopifyTokenPattern, "SHOPIFY_ACCESS_TOKEN=***REMOVED***"
        $Content = $Content -replace $ApiKeyPattern, "API_KEY=***REMOVED***"
        
        # Guardar cambios
        $Content | Out-File -FilePath $File -Encoding utf8
        
        Write-Host "  ✅ Archivo actualizado" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️ Archivo no encontrado: $File" -ForegroundColor Yellow
    }
}

Write-Host "`nPara otros archivos de despliegue, se recomienda actualizarlos para usar deploy_common.ps1" -ForegroundColor Cyan
Write-Host "Ejemplo:" -ForegroundColor Cyan
Write-Host '. .\deploy_common.ps1' -ForegroundColor Gray
Write-Host '$SecretsLoaded = Load-SecretVariables' -ForegroundColor Gray
Write-Host '$EnvVars = Get-EnvVarsString' -ForegroundColor Gray
Write-Host 'gcloud run deploy ... --set-env-vars "$EnvVars" ...' -ForegroundColor Gray

Write-Host "`n✅ Archivos actualizados localmente. Sigue los pasos anteriores para limpiar el historial de Git." -ForegroundColor Green
