# Script mejorado para ejecutar pruebas del sistema de recomendaciones
# Version simplificada sin emojis para evitar problemas de codificacion

param (
    [string]$TestType = "all",
    [switch]$Verbose = $false,
    [switch]$Coverage = $false,
    [switch]$XmlReport = $false,
    [switch]$VerifyFixes = $true
)

# Configuracion de colores
$Green = [ConsoleColor]::Green
$Red = [ConsoleColor]::Red
$Yellow = [ConsoleColor]::Yellow
$Cyan = [ConsoleColor]::Cyan
$Magenta = [ConsoleColor]::Magenta

# Mostrar encabezado
Write-Host "`n===============================================" -ForegroundColor $Cyan
Write-Host " Sistema de Recomendaciones - Pruebas v2.0" -ForegroundColor $Cyan
Write-Host "===============================================" -ForegroundColor $Cyan
Write-Host "Tipo de prueba: $TestType" -ForegroundColor $Cyan
Write-Host "Verbose: $Verbose" -ForegroundColor $Cyan
Write-Host "Coverage: $Coverage" -ForegroundColor $Cyan
Write-Host "XML Report: $XmlReport" -ForegroundColor $Cyan
Write-Host "Verify Fixes: $VerifyFixes" -ForegroundColor $Cyan
Write-Host "-----------------------------------------------`n" -ForegroundColor $Cyan

# Funcion para verificar correcciones
function Verify-TestFixes {
    Write-Host "[INFO] Verificando correcciones implementadas..." -ForegroundColor $Yellow
    
    if (Test-Path "verify_test_fixes.py") {
        try {
            $verifyResult = python verify_test_fixes.py
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[OK] Todas las correcciones verificadas correctamente" -ForegroundColor $Green
                return $true
            } else {
                Write-Host "[ERROR] Algunas correcciones necesitan atencion:" -ForegroundColor $Red
                Write-Host $verifyResult -ForegroundColor $Yellow
                return $false
            }
        } catch {
            Write-Host "[WARN] Error ejecutando verificacion: $_" -ForegroundColor $Yellow
            Write-Host "Continuando con las pruebas..." -ForegroundColor $Yellow
            return $true
        }
    } else {
        Write-Host "[WARN] Script de verificacion no encontrado, continuando..." -ForegroundColor $Yellow
        return $true
    }
}

# Verificar correcciones si esta habilitado
if ($VerifyFixes) {
    $fixesOk = Verify-TestFixes
    if (-not $fixesOk) {
        Write-Host "`n[ERROR] Se encontraron problemas en las correcciones." -ForegroundColor $Red
        Write-Host "Deseas continuar con las pruebas de todos modos? (y/N)" -ForegroundColor $Yellow
        $continue = Read-Host
        if ($continue -ne "y" -and $continue -ne "Y" -and $continue -ne "yes") {
            Write-Host "Deteniendo ejecucion. Corrige los problemas e intenta de nuevo." -ForegroundColor $Red
            exit 1
        }
    }
}

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
Write-Host "Activando entorno virtual de pruebas ($venvPath)..." -ForegroundColor $Yellow
& "$venvPath\Scripts\Activate.ps1"
if (-not $?) {
    Write-Host "Error al activar entorno virtual" -ForegroundColor $Red
    exit 1
}

# Verificar entorno activado
if (-not $env:VIRTUAL_ENV) {
    Write-Host "ERROR: Entorno virtual no activado correctamente" -ForegroundColor $Red
    exit 1
}
Write-Host "Entorno virtual activado correctamente: $env:VIRTUAL_ENV" -ForegroundColor $Green

# Lista de dependencias de pruebas
$testDeps = @(
    "pytest",
    "pytest-asyncio", 
    "pytest-cov",
    "httpx"
)

Write-Host "Verificando e instalando dependencias de pruebas..." -ForegroundColor $Yellow
foreach ($dep in $testDeps) {
    $installed = pip list | Select-String -Pattern "^$dep\s+"
    if (-not $installed) {
        Write-Host "Instalando $dep..." -ForegroundColor $Yellow
        pip install $dep
        if (-not $?) {
            Write-Host "Error al instalar $dep" -ForegroundColor $Red
            exit 1
        }
    } else {
        Write-Host "[OK] $dep ya instalado" -ForegroundColor $Green
    }
}

# Instalar dependencias del proyecto
Write-Host "Instalando dependencias del proyecto..." -ForegroundColor $Yellow
pip install -e .
if (-not $?) {
    Write-Host "Error al instalar dependencias del proyecto" -ForegroundColor $Red
    exit 1
}

# Configurar variables de entorno para pruebas
Write-Host "Configurando variables de entorno para pruebas..." -ForegroundColor $Yellow
$env:TEST_MODE = "true"
$env:API_KEY = "test-api-key-123"
$env:DEBUG = "true"
$env:METRICS_ENABLED = "true"
$env:EXCLUDE_SEEN_PRODUCTS = "true"
$env:USE_REDIS_CACHE = "false"
$env:GOOGLE_PROJECT_NUMBER = "test-project-123"
$env:GOOGLE_LOCATION = "global"
$env:GOOGLE_CATALOG = "test_catalog"
$env:GOOGLE_SERVING_CONFIG = "test_config"
$env:STARTUP_TIMEOUT = "10.0"

Write-Host "API_KEY para pruebas: $env:API_KEY" -ForegroundColor $Magenta
Write-Host "TEST_MODE: $env:TEST_MODE" -ForegroundColor $Magenta

# Preparar comando de pytest
$pytestCmd = "pytest"

if ($Verbose) {
    $pytestCmd += " -v -s"
} else {
    $pytestCmd += " -v"
}

if ($Coverage) {
    $pytestCmd += " --cov=src --cov-report=term-missing --cov-report=html:coverage"
}

if ($XmlReport) {
    $pytestCmd += " --junitxml=test-results.xml"
}

$pytestCmd += " --tb=short --disable-warnings"

# Determinar que pruebas ejecutar
switch ($TestType) {
    "unit" {
        $testPath = "tests/unit"
        Write-Host "Ejecutando pruebas unitarias..." -ForegroundColor $Yellow
    }
    "integration" {
        $testPath = "tests/integration"
        Write-Host "Ejecutando pruebas de integracion..." -ForegroundColor $Yellow
    }
    "performance" {
        $testPath = "tests/performance/test_api_performance.py"
        Write-Host "Ejecutando pruebas de rendimiento..." -ForegroundColor $Yellow
    }
    "api-flow" {
        $testPath = "tests/integration/test_api_flow.py"
        Write-Host "Ejecutando pruebas de flujo de API..." -ForegroundColor $Yellow
    }
    "all" {
        $testPath = "tests/unit tests/integration"
        Write-Host "Ejecutando todas las pruebas..." -ForegroundColor $Yellow
    }
    default {
        Write-Host "Tipo de prueba no valido: $TestType" -ForegroundColor $Red
        Write-Host "Opciones validas: all, unit, integration, performance, api-flow" -ForegroundColor $Red
        exit 1
    }
}

# Ejecutar pruebas
$pytestCmd += " $testPath"
Write-Host "`nEjecutando: $pytestCmd" -ForegroundColor $Cyan
Write-Host "===========================================" -ForegroundColor $Cyan

$startTime = Get-Date

try {
    Invoke-Expression $pytestCmd
    $testExitCode = $LASTEXITCODE
} catch {
    Write-Host "Error ejecutando pytest: $_" -ForegroundColor $Red
    $testExitCode = 1
}

$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host "`n===========================================" -ForegroundColor $Cyan
Write-Host "Tiempo total de ejecucion: $($duration.TotalSeconds) segundos" -ForegroundColor $Cyan

# Verificar resultado
if ($testExitCode -eq 0) {
    Write-Host "`n[SUCCESS] Pruebas completadas con exito!" -ForegroundColor $Green
    
    if ($Coverage) {
        Write-Host "[INFO] Informe de cobertura generado en directorio coverage" -ForegroundColor $Green
    }
    
    if ($XmlReport) {
        Write-Host "[INFO] Informe XML generado como test-results.xml" -ForegroundColor $Green
    }
    
    Write-Host "`nResumen de ejecucion:" -ForegroundColor $Cyan
    Write-Host "   Tipo de prueba: $TestType" -ForegroundColor $White
    Write-Host "   Duracion: $($duration.TotalSeconds) segundos" -ForegroundColor $White
    Write-Host "   Estado: EXITOSO" -ForegroundColor $Green
    
    exit 0
} else {
    Write-Host "`n[FAILED] Algunas pruebas han fallado" -ForegroundColor $Red
    
    Write-Host "`nSugerencias para debugging:" -ForegroundColor $Yellow
    Write-Host "   Ejecutar con mas detalle: $pytestCmd -s --tb=long" -ForegroundColor $White
    Write-Host "   Ejecutar una prueba especifica: pytest tests/integration/test_api_flow.py::test_nombre -v" -ForegroundColor $White
    Write-Host "   Verificar correcciones: python verify_test_fixes.py" -ForegroundColor $White
    
    Write-Host "`nResumen de ejecucion:" -ForegroundColor $Cyan
    Write-Host "   Tipo de prueba: $TestType" -ForegroundColor $White
    Write-Host "   Duracion: $($duration.TotalSeconds) segundos" -ForegroundColor $White
    Write-Host "   Estado: FALLO" -ForegroundColor $Red
    Write-Host "   Codigo de salida: $testExitCode" -ForegroundColor $White
    
    exit $testExitCode
}
