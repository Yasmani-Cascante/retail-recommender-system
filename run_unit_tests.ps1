# Script simple para ejecutar pruebas unitarias

# Verificar si estamos en un entorno virtual y activarlo si es necesario
if ($null -eq $env:VIRTUAL_ENV) {
    # Usar el entorno virtual de pruebas si existe
    if (Test-Path "venv.test\Scripts\Activate.ps1") {
        Write-Host "Activando entorno virtual de pruebas..."
        & "venv.test\Scripts\Activate.ps1"
    } elseif (Test-Path "venv\Scripts\Activate.ps1") {
        Write-Host "Activando entorno virtual..."
        & "venv\Scripts\Activate.ps1"
    } else {
        Write-Host "ADVERTENCIA: No se encontró un entorno virtual. Las pruebas podrían fallar si faltan dependencias."
    }
}

# Asegurarse de que httpx está instalado (necesario para TestClient)
Write-Host "Verificando instalación de httpx..."
pip install httpx -q

# Ejecutar las pruebas unitarias
Write-Host "Ejecutando pruebas unitarias..."
pytest tests/unit -v
