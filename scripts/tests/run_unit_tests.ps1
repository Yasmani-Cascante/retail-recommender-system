# Script para ejecutar pruebas unitarias con el entorno de prueba

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

# Asegurar que pytest y pytest-asyncio están instalados
Write-Host "Verificando instalación de pytest y pytest-asyncio..."
pip install pytest pytest-asyncio -q

# Si existe un archivo .env, hacer una copia de seguridad
if (Test-Path ".env") {
    Write-Host "Haciendo copia de seguridad del archivo .env"
    Copy-Item -Force ".env" ".env.bak"
}

# Ejecutar las pruebas unitarias
Write-Host "Ejecutando pruebas unitarias..."
pytest tests/unit -v --asyncio-mode=strict

# Restaurar .env original si existe
if (Test-Path ".env.bak") {
    Write-Host "Restaurando archivo .env original"
    Move-Item -Force ".env.bak" ".env"
}
