@echo off
echo ======================================
echo  TESTING REAL SHOPIFY MCP BRIDGE
echo ======================================

cd /d "C:\Users\yasma\Desktop\retail-recommender-system\src\api\mcp\nodejs_bridge"

echo.
echo ✅ Installing test dependencies...
npm install axios

echo.
echo 🧪 Running integration tests...
echo 📍 Target: http://localhost:3001
echo.

node test-integration.js

echo.
echo ✅ Tests completed!
pause
