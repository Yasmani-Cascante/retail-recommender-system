# Script para instalar todas las dependencias de prueba necesarias

# Configuración de colores para la salida
$Green = [ConsoleColor]::Green
$Red = [ConsoleColor]::Red
$Yellow = [ConsoleColor]::Yellow
$Cyan = [ConsoleColor]::Cyan

# Mostrar encabezado
Write-Host "`n=======================================" -ForegroundColor $Cyan
Write-Host " Instalación de Dependencias de Prueba" -ForegroundColor $Cyan
Write-Host "=======================================" -ForegroundColor $Cyan

# Verificar si estamos en un entorno virtual
$inVenv = $env:VIRTUAL_ENV -ne $null
if (-not $inVenv) {
    Write-Host "No se detectó un entorno virtual activo." -ForegroundColor $Yellow
    
    # Verificar si existe el entorno de pruebas
    $venvPath = "venv.test"
    if (-not (Test-Path $venvPath)) {
        Write-Host "Creando entorno virtual para pruebas en '$venvPath'..." -ForegroundColor $Yellow
        python -m venv $venvPath
        if (-not $?) {
            Write-Host "Error al crear entorno virtual" -ForegroundColor $Red
            exit 1
        }
    }
    
    # Activar entorno virtual
    Write-Host "Activando entorno virtual de pruebas..." -ForegroundColor $Yellow
    & "$venvPath\Scripts\Activate.ps1"
    if (-not $?) {
        Write-Host "Error al activar entorno virtual" -ForegroundColor $Red
        exit 1
    }
} else {
    Write-Host "Usando entorno virtual activo: $env:VIRTUAL_ENV" -ForegroundColor $Green
}

# Lista de dependencias necesarias para las pruebas
$testDeps = @(
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "httpx",
    "locust",
    "fastapi",
    "uvicorn",
    "starlette"
)

# Instalar cada dependencia
Write-Host "`nInstalando dependencias de prueba..." -ForegroundColor $Yellow
foreach ($dep in $testDeps) {
    Write-Host "Instalando $dep..." -ForegroundColor $Yellow
    pip install $dep
    if (-not $?) {
        Write-Host "⚠️ Advertencia: Error al instalar $dep" -ForegroundColor $Red
        # Continuamos a pesar de errores para intentar instalar el máximo posible
    }
}

# Instalar el proyecto en modo desarrollo
Write-Host "`nInstalando el proyecto en modo desarrollo..." -ForegroundColor $Yellow
pip install -e .
if (-not $?) {
    Write-Host "⚠️ Advertencia: Error al instalar el proyecto" -ForegroundColor $Red
}

# Mostrar versiones instaladas
Write-Host "`nDependencias instaladas:" -ForegroundColor $Green
pip list | Select-String -Pattern $(($testDeps -join "|") + "|retail-recommender-system")

Write-Host "`n✅ Instalación de dependencias completada" -ForegroundColor $Green
Write-Host "Ahora puede ejecutar las pruebas con: .\run_tests.ps1" -ForegroundColor $Green
