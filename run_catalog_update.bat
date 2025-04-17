@echo off
echo ==============================================
echo  ACTUALIZACION DE CATALOGO DE SHOPIFY
echo ==============================================
echo.

echo Paso 1: Verificando los productos de Shopify...
python verify_shopify_products.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: La verificacion de productos fallo.
    exit /b 1
)

echo.
echo Paso 2: Actualizando el catalogo completo...
echo ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del tamano del catalogo.
echo.
set /p CONTINUE=Desea continuar? (s/n): 
if /i "%CONTINUE%" NEQ "s" (
    echo Operacion cancelada.
    exit /b 0
)

python update_catalog.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: La actualizacion del catalogo fallo.
    exit /b 1
)

echo.
echo ==============================================
echo  PROCESO COMPLETADO EXITOSAMENTE
echo ==============================================
echo.
echo Resumen:
echo - Se ha verificado la cantidad de productos en Shopify
echo - Se ha actualizado el catalogo completo en Google Cloud Retail API
echo.
echo Para ver los productos en Google Cloud Console:
echo 1. Ve a: https://console.cloud.google.com/retail/
echo 2. Selecciona tu proyecto
echo 3. Ve a "Catalogs" y selecciona "default_catalog"
echo 4. Revisa la rama "0" para ver todos los productos importados
echo.
pause