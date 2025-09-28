@echo off
echo ======================================
echo  INSTALANDO AXIOS Y EJECUTANDO TESTS
echo ======================================

cd /d "C:\Users\yasma\Desktop\retail-recommender-system\src\api\mcp\nodejs_bridge"

echo.
echo ✅ Instalando axios...
npm install axios

echo.
echo 🧪 Ejecutando tests de integración...
node test-integration.js

echo.
echo ✅ Tests completados!
pause
