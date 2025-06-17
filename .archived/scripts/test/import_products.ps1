# Script PowerShell para importar productos a Google Retail API

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Verificar la estructura de la API primero
Write-Host "Verificando la estructura de la API de Retail..." -ForegroundColor Green
python check_api_structure.py

# Preguntar si se desea continuar
$response = Read-Host -Prompt "`n¿Deseas continuar con la importación de productos? (S/N)"
if ($response -eq "S" -or $response -eq "s") {
    Write-Host "Importando productos a Google Retail API..." -ForegroundColor Green
    python test_import_fixed.py
    
    # Verificar productos en el catálogo después de la importación
    Write-Host "`nVerificando productos en el catálogo después de la importación..." -ForegroundColor Green
    python check_catalog.py
} else {
    Write-Host "Importación cancelada por el usuario" -ForegroundColor Yellow
}

Write-Host "`nProceso completado." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
