# Script PowerShell para la versión final de importación

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Ejecutar el script de importación final
Write-Host "Ejecutando la versión final de importación..." -ForegroundColor Green
python test_import_final.py

Write-Host "`nImportación completada. Verificando catálogo..." -ForegroundColor Green
python check_catalog.py

Write-Host "`nProceso completado." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
