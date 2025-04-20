#!/bin/bash
# Script para ejecutar pruebas unitarias para el sistema de recomendaciones
# Autor: Team de Arquitectura
# Fecha: 20.04.2025

echo -e "\033[0;32mEjecutando pruebas unitarias para el sistema de recomendaciones...\033[0m"

# Verificar si el entorno virtual está activado
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "\033[0;33mActivando entorno virtual de pruebas...\033[0m"
    
    # Verificar si existe el entorno virtual de pruebas
    if [ -d "venv.test" ]; then
        # Activar entorno virtual
        source venv.test/bin/activate
    else
        # Crear y activar entorno virtual si no existe
        echo -e "\033[0;33mCreando entorno virtual de pruebas...\033[0m"
        python -m venv venv.test
        source venv.test/bin/activate
        
        # Instalar dependencias necesarias
        echo -e "\033[0;33mInstalando dependencias de pruebas...\033[0m"
        pip install -r requirements.txt
        pip install pytest pytest-asyncio
    fi
fi

# Establecer variables de entorno de prueba
echo -e "\033[0;33mConfigurando variables de entorno para pruebas...\033[0m"
export GOOGLE_PROJECT_NUMBER="test-project-123"
export GOOGLE_LOCATION="global"
export GOOGLE_CATALOG="test-catalog"
export GOOGLE_SERVING_CONFIG="test-config"
export API_KEY="test-api-key-123"
export DEBUG="true"
export METRICS_ENABLED="true"
export EXCLUDE_SEEN_PRODUCTS="true"
export VALIDATE_PRODUCTS="true"
export USE_FALLBACK="true"
export CONTENT_WEIGHT="0.5"

# Ejecutar pruebas unitarias
echo -e "\033[0;36mEjecutando pruebas unitarias...\033[0m"
python -m pytest tests/unit -v

# Capturar el código de salida
TEST_RESULT=$?

# Mostrar resultados
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "\n\033[0;32m✅ Todas las pruebas unitarias pasaron exitosamente!\033[0m"
else
    echo -e "\n\033[0;31m❌ Algunas pruebas unitarias fallaron. Por favor, revise los errores arriba.\033[0m"
fi

# Devolver el código de salida
exit $TEST_RESULT
