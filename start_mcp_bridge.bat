@echo off
REM start_mcp_bridge.bat - Script para iniciar el MCP bridge en Windows

echo 🚀 Iniciando MCP Bridge...

REM Ir al directorio del bridge
cd %~dp0\src\api\mcp\nodejs_bridge

REM Asegurarse de que los módulos están instalados
if not exist node_modules (
    echo 📦 Instalando dependencias Node.js...
    call npm install
)

REM Iniciar el servidor
echo 🌐 Iniciando servidor Node.js...
node server.js
