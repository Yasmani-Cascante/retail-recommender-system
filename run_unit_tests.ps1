# Script para ejecutar pruebas unitarias para el sistema de recomendaciones
# Autor: Team de Arquitectura
# Fecha: 20.04.2025

Write-Host "Ejecutando pruebas unitarias para el sistema de recomendaciones..." -ForegroundColor Green

# Verificar si el entorno virtual está activado
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Activando entorno virtual de pruebas..." -ForegroundColor Yellow
    
    # Verificar si existe el entorno virtual de pruebas
    if (Test-Path "venv.test") {
        # Activar entorno virtual
        & .\venv.test\Scripts\Activate.ps1
    } else {
        # Crear y activar entorno virtual si no existe
        Write-Host "Creando entorno virtual de pruebas..." -ForegroundColor Yellow
        python -m venv venv.test
        & .\venv.test\Scripts\Activate.ps1
        
        # Instalar dependencias necesarias
        Write-Host "Instalando dependencias de pruebas..." -ForegroundColor Yellow
        pip install -r requirements.txt
        pip install pytest pytest-asyncio httpx
    }
}

# Establecer variables de entorno de prueba
Write-Host "Configurando variables de entorno para pruebas..." -ForegroundColor Yellow
$env:GOOGLE_PROJECT_NUMBER = "test-project-123"
$env:GOOGLE_LOCATION = "global"
$env:GOOGLE_CATALOG = "test-catalog"
$env:GOOGLE_SERVING_CONFIG = "test-config"
$env:API_KEY = "test-api-key-123"
$env:DEBUG = "true"
$env:METRICS_ENABLED = "true"
$env:EXCLUDE_SEEN_PRODUCTS = "true"
$env:VALIDATE_PRODUCTS = "true"
$env:USE_FALLBACK = "true"
$env:CONTENT_WEIGHT = "0.5"

# Ejecutar pruebas unitarias
Write-Host "Ejecutando pruebas unitarias..." -ForegroundColor Cyan
pytest tests/unit -v

# Capturar el código de salida
$testResult = $LASTEXITCODE

# Mostrar resultados
if ($testResult -eq 0) {
    Write-Host "`n✅ Todas las pruebas unitarias pasaron exitosamente!" -ForegroundColor Green
} else {
    Write-Host "`n❌ Algunas pruebas unitarias fallaron. Por favor, revise los errores arriba." -ForegroundColor Red
}

# Devolver el código de salida
exit $testResult
