# Script simplificado para reemplazar secretos en archivos
Write-Host "Reemplazando secretos en archivos de despliegue..." -ForegroundColor Yellow

# Función para reemplazar secretos en archivos
function Replace-Secret {
    param (
        [string]$FilePath,
        [string]$SecretPattern,
        [string]$Replacement
    )
    
    if (Test-Path $FilePath) {
        $content = Get-Content $FilePath -Raw
        
        if ($content -match $SecretPattern) {
            $newContent = $content -replace $SecretPattern, $Replacement
            Set-Content -Path $FilePath -Value $newContent -Encoding UTF8
            return $true
        }
        return $false
    } else {
        Write-Host "El archivo $FilePath no existe." -ForegroundColor Yellow
        return $false
    }
}

# Lista de archivos a limpiar
$filesToClean = @(
    "deploy_tfidf_events_final.ps1",
    "deploy_tfidf_full_metrics.ps1",
    "deploy_tfidf_shopify.ps1",
    "deploy_tfidf_shopify.py",
    "deploy_tfidf_shopify_improved.ps1"
)

$pattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
$replacement = 'SHOPIFY_ACCESS_TOKEN="REMOVED_FOR_SECURITY"'

# Procesar cada archivo
foreach ($file in $filesToClean) {
    Write-Host "Procesando $file..." -ForegroundColor Cyan
    $result = Replace-Secret -FilePath $file -SecretPattern $pattern -Replacement $replacement
    
    if ($result) {
        Write-Host "  ✅ Secretos reemplazados exitosamente" -ForegroundColor Green
    } else {
        Write-Host "  ℹ️ No se encontraron secretos para reemplazar" -ForegroundColor Yellow
    }
}

Write-Host "`nProceso completado." -ForegroundColor Green
Write-Host "Ahora debes:" -ForegroundColor Cyan
Write-Host "1. Añadir los cambios: git add -A" -ForegroundColor White
Write-Host "2. Crear un commit: git commit -m `"Removed sensitive information`"" -ForegroundColor White
Write-Host "3. Hacer push: git push" -ForegroundColor White
Write-Host "`nSi GitHub sigue bloqueando el push, visita el enlace que proporciona" -ForegroundColor Yellow
Write-Host "para desbloquear temporalmente el secreto detectado." -ForegroundColor Yellow
