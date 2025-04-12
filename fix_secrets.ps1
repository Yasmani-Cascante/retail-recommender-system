# Script simplificado para reemplazar secretos
Write-Host "Reemplazando secretos en archivos..." -ForegroundColor Cyan

# Lista de archivos a procesar
$files = @(
    "deploy_tfidf_events_final.ps1",
    "deploy_tfidf_full_metrics.ps1",
    "deploy_tfidf_shopify.ps1",
    "deploy_tfidf_shopify.py",
    "deploy_tfidf_shopify_improved.ps1"
)

# Patrón para buscar (token de Shopify)
$pattern = 'SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+'
$replacement = 'SHOPIFY_ACCESS_TOKEN="REMOVED_FOR_SECURITY"'

# Procesa cada archivo
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Procesando $file..." -ForegroundColor Yellow
        
        # Leer el contenido del archivo
        $content = Get-Content -Path $file -Raw
        
        # Realizar el reemplazo
        if ($content -match $pattern) {
            $newContent = $content -replace $pattern, $replacement
            Set-Content -Path $file -Value $newContent -Encoding UTF8
            Write-Host "  ✓ Secretos reemplazados exitosamente" -ForegroundColor Green
        } else {
            Write-Host "  - No se encontraron secretos para reemplazar" -ForegroundColor Yellow
        }
    } else {
        Write-Host "El archivo $file no existe." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Proceso completado." -ForegroundColor Green
Write-Host "Ahora ejecuta:"
Write-Host "  git add -A" -ForegroundColor White
Write-Host "  git commit -m 'Removed sensitive information'" -ForegroundColor White
Write-Host "  git push" -ForegroundColor White
