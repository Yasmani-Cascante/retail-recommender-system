# install_mcp_dependencies.ps1
# Script para instalar dependencias MCP

Write-Host "🚀 Instalando dependencias MCP..." -ForegroundColor Green

# Activar entorno virtual
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
    Write-Host "✅ Entorno virtual activado" -ForegroundColor Green
} else {
    Write-Host "⚠️ Entorno virtual no encontrado, usando Python global" -ForegroundColor Yellow
}

# Instalar dependencias MCP
Write-Host "📦 Instalando dependencias desde requirements_mcp.txt..." -ForegroundColor Cyan
pip install -r requirements_mcp.txt

# Verificar instalación
Write-Host "🔍 Verificando instalaciones..." -ForegroundColor Cyan

try {
    python -c "import anthropic; print('✅ anthropic instalado correctamente')"
} catch {
    Write-Host "❌ Error instalando anthropic" -ForegroundColor Red
}

try {
    python -c "import httpx; print('✅ httpx instalado correctamente')"
} catch {
    Write-Host "❌ Error instalando httpx" -ForegroundColor Red
}

try {
    python -c "from pydantic import BaseModel; print('✅ pydantic actualizado correctamente')"
} catch {
    Write-Host "❌ Error con pydantic" -ForegroundColor Red
}

Write-Host "🎉 Instalación de dependencias completada!" -ForegroundColor Green