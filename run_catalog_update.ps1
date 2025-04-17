# PowerShell script para actualizar el catálogo de Shopify

Write-Host "=============================================="
Write-Host " ACTUALIZACIÓN DE CATÁLOGO DE SHOPIFY"
Write-Host "=============================================="
Write-Host ""

Write-Host "Paso 1: Verificando los productos de Shopify..." -ForegroundColor Yellow
python verify_shopify_products.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: La verificación de productos falló." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Paso 2: Actualizando el catálogo completo..." -ForegroundColor Yellow
Write-Host "ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del tamaño del catálogo." -ForegroundColor DarkYellow
Write-Host ""
$confirmation = Read-Host "¿Desea continuar? (s/n)"

if ($confirmation.ToLower() -ne "s") {
    Write-Host "Operación cancelada por el usuario." -ForegroundColor Yellow
    exit 0
}

python update_catalog.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: La actualización del catálogo falló." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host " PROCESO COMPLETADO EXITOSAMENTE" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Resumen:" -ForegroundColor Cyan
Write-Host "- Se ha verificado la cantidad de productos en Shopify" -ForegroundColor White
Write-Host "- Se ha actualizado el catálogo completo en Google Cloud Retail API" -ForegroundColor White
Write-Host ""
Write-Host "Para ver los productos en Google Cloud Console:" -ForegroundColor Cyan
Write-Host "1. Ve a: https://console.cloud.google.com/retail/" -ForegroundColor White
Write-Host "2. Selecciona tu proyecto" -ForegroundColor White
Write-Host "3. Ve a 'Catalogs' y selecciona 'default_catalog'" -ForegroundColor White
Write-Host "4. Revisa la rama '0' para ver todos los productos importados" -ForegroundColor White
Write-Host ""
Read-Host "Presiona Enter para salir"