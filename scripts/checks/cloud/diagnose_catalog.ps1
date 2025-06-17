# Script para diagnosticar y resolver problemas del catálogo

# Activar el entorno virtual si existe
if (Test-Path .\venv\Scripts\Activate.ps1) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}
else {
    Write-Host "⚠️ Entorno virtual no encontrado. Utilizando Python del sistema" -ForegroundColor Yellow
}

# Verificar el entorno
Write-Host "Verificando variables de entorno..." -ForegroundColor Green
python reset_client.py

# Verificar productos en el catálogo
Write-Host "`nVerificando productos en el catálogo..." -ForegroundColor Green
python check_catalog.py

# Preguntar si se desea importar productos
$response = Read-Host -Prompt "`n¿Deseas importar productos a Google Retail API? (S/N)"
if ($response -eq "S" -or $response -eq "s") {
    Write-Host "Importando productos..." -ForegroundColor Green
    python test_import.py
    
    # Verificar nuevamente después de la importación
    Write-Host "`nVerificando productos después de la importación..." -ForegroundColor Green
    python check_catalog.py
}

Write-Host "`nDiagnóstico completado." -ForegroundColor Green
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
