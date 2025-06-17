# Script para corregir la importación de productos a Google Retail API

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Verificar configuración
Write-Host "Verificando configuración y catálogos..." -ForegroundColor Green
python check_catalog.py

# Ejecutar la importación con la estructura correcta
Write-Host "`nImportando productos con la estructura actualizada..." -ForegroundColor Green
python import_products.py

# Verificar nuevamente después de la importación
Write-Host "`nVerificando productos después de la importación..." -ForegroundColor Green
python check_catalog.py

# Sugerir reiniciar la aplicación
Write-Host "`nProceso de importación completado." -ForegroundColor Green
Write-Host "Para utilizar el sistema de recomendaciones, reinicia la aplicación con:" -ForegroundColor Cyan
Write-Host "python run_patched.py" -ForegroundColor Cyan
Write-Host "`nPresiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
