@echo off
REM start_mcp_bridge_mock.bat - Script para iniciar el MCP bridge en modo mock

echo 🚀 Iniciando MCP Bridge en modo MOCK...

REM Ir al directorio del bridge
cd %~dp0\src\api\mcp\nodejs_bridge

REM Asegurarse de que los módulos están instalados
if not exist node_modules (
    echo 📦 Instalando dependencias Node.js...
    call npm install
)

REM Iniciar el servidor con Mock MCP
echo 🌐 Iniciando servidor Node.js con Mock MCP...
set USE_MOCK_MCP=true
node server.js
