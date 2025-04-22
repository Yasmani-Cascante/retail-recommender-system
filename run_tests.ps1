# Script para ejecutar pruebas del sistema de recomendaciones
# Este script ejecuta todas las pruebas o un conjunto específico según los parámetros

param (
    [string]$TestType = "all",  # Opciones: "all", "unit", "integration", "performance"
    [switch]$Verbose = $false,  # Mostrar salida detallada
    [switch]$Coverage = $false, # Generar informe de cobertura
    [switch]$XmlReport = $false # Generar informe XML para CI/CD
)

# Configuración de colores para la salida
$Green = [ConsoleColor]::Green
$Red = [ConsoleColor]::Red
$Yellow = [ConsoleColor]::Yellow
$Cyan = [ConsoleColor]::Cyan

# Mostrar encabezado
Write-Host "`n=======================================" -ForegroundColor $Cyan
Write-Host " Sistema de Recomendaciones - Pruebas" -ForegroundColor $Cyan
Write-Host "=======================================" -ForegroundColor $Cyan
Write-Host "Tipo de prueba: $TestType" -ForegroundColor $Cyan
Write-Host "Verbose: $Verbose" -ForegroundColor $Cyan
Write-Host "Coverage: $Coverage" -ForegroundColor $Cyan
Write-Host "XML Report: $XmlReport" -ForegroundColor $Cyan
Write-Host "---------------------------------------`n" -ForegroundColor $Cyan

# Asegurar que el entorno de pruebas existe
$venvPath = "venv.test"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creando entorno virtual para pruebas..." -ForegroundColor $Yellow
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

# Instalar dependencias si no están ya instaladas
$testDeps = @(
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "locust",
    "httpx"
)

Write-Host "Verificando dependencias de pruebas..." -ForegroundColor $Yellow
foreach ($dep in $testDeps) {
    $installed = pip list | Select-String -Pattern "^$dep\s+"
    if (-not $installed) {
        Write-Host "Instalando $dep..." -ForegroundColor $Yellow
        pip install $dep
        if (-not $?) {
            Write-Host "Error al instalar $dep" -ForegroundColor $Red
            exit 1
        }
    }
}

# Asegurar que las dependencias del proyecto están instaladas
Write-Host "Instalando dependencias del proyecto..." -ForegroundColor $Yellow
pip install -e .
if (-not $?) {
    Write-Host "Error al instalar dependencias del proyecto" -ForegroundColor $Red
    exit 1
}

# Preparar comando de pytest
$pytestCmd = "pytest"

# Añadir flags según parámetros
if ($Verbose) {
    $pytestCmd += " -v"
}

if ($Coverage) {
    $pytestCmd += " --cov=src --cov-report=term --cov-report=html:coverage"
}

if ($XmlReport) {
    $pytestCmd += " --junitxml=test-results.xml"
}

# Determinar qué pruebas ejecutar
switch ($TestType) {
    "unit" {
        $testPath = "tests/unit"
        Write-Host "Ejecutando pruebas unitarias..." -ForegroundColor $Yellow
    }
    "integration" {
        $testPath = "tests/integration"
        Write-Host "Ejecutando pruebas de integración..." -ForegroundColor $Yellow
    }
    "performance" {
        $testPath = "tests/performance/test_api_performance.py"
        Write-Host "Ejecutando pruebas de rendimiento..." -ForegroundColor $Yellow
    }
    "all" {
        $testPath = "tests/unit tests/integration"
        Write-Host "Ejecutando todas las pruebas (excepto rendimiento)..." -ForegroundColor $Yellow
    }
    default {
        Write-Host "Tipo de prueba no válido: $TestType" -ForegroundColor $Red
        Write-Host "Opciones válidas: all, unit, integration, performance" -ForegroundColor $Red
        exit 1
    }
}

# Ejecutar pruebas
$pytestCmd += " $testPath"
Write-Host "Ejecutando: $pytestCmd" -ForegroundColor $Yellow
Invoke-Expression $pytestCmd

# Verificar resultado
if ($?) {
    Write-Host "`n✅ Pruebas completadas con éxito" -ForegroundColor $Green
    
    # Ejecutar pruebas de carga con Locust si se solicitan
    if ($TestType -eq "performance" -and $args -contains "load") {
        Write-Host "`n🔄 Iniciando pruebas de carga con Locust..." -ForegroundColor $Yellow
        Write-Host "Nota: Locust iniciará una interfaz web en http://localhost:8089" -ForegroundColor $Yellow
        Write-Host "Presiona Ctrl+C para detener las pruebas de carga" -ForegroundColor $Yellow
        
        # Iniciar Locust
        locust -f tests/performance/locustfile.py
    }
    
    # Mostrar información adicional
    if ($Coverage) {
        Write-Host "`n📊 Informe de cobertura generado en el directorio 'coverage'" -ForegroundColor $Green
    }
    
    if ($XmlReport) {
        Write-Host "📄 Informe XML generado como 'test-results.xml'" -ForegroundColor $Green
    }
    
    exit 0
} else {
    Write-Host "`n❌ Algunas pruebas han fallado" -ForegroundColor $Red
    exit 1
}
