@echo off
echo ======================================
echo  REAL SHOPIFY MCP BRIDGE - START
echo ======================================

cd /d "C:\Users\yasma\Desktop\retail-recommender-system\src\api\mcp\nodejs_bridge"

echo.
echo ✅ 1. Checking Node.js version...
node --version

echo.
echo ✅ 2. Installing dependencies...
npm install

echo.
echo ✅ 3. Starting Real Shopify MCP Bridge server...
echo 📍 URL: http://localhost:3001
echo 🔧 Environment: development
echo 🏪 Shopify: ai-shoppings.myshopify.com
echo.

npm start
