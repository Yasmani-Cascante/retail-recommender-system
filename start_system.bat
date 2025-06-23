@echo off
REM start_system.bat - Script para iniciar todo el sistema

echo 🚀 Iniciando sistema completo de recomendaciones...

REM Crear nuevas ventanas para cada componente
start cmd /k "cd %~dp0\src\api\mcp\nodejs_bridge && npm start"
echo 🌉 Bridge MCP iniciado en nueva ventana

echo ⏳ Esperando 5 segundos para que el bridge se inicialice...
timeout /t 5 /nobreak > nul

start cmd /k "cd %~dp0 && python src/api/run.py"
echo 🚀 API FastAPI iniciada en nueva ventana

echo ✅ Sistema completo iniciado. Acceso:
echo   - API principal: http://localhost:8000
echo   - Bridge MCP: http://localhost:3001
echo   - Monitor MCP: http://localhost:8000/static/mcp_monitor.html
echo.
echo Para detener el sistema, cierre las ventanas de comandos.
