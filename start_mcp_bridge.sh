#!/bin/bash
# start_mcp_bridge.sh - Script para iniciar el MCP bridge

echo "🚀 Iniciando MCP Bridge..."

# Ir al directorio del bridge
cd "$(dirname "$0")/src/api/mcp/nodejs_bridge"

# Asegurarse de que los módulos están instalados
if [ ! -d "node_modules" ]; then
    echo "📦 Instalando dependencias Node.js..."
    npm install
fi

# Iniciar el servidor
echo "🌐 Iniciando servidor Node.js..."
node server.js
