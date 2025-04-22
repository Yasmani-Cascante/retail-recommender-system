# Plan de Pruebas para la Arquitectura Unificada

Este directorio contiene el plan de pruebas completo para validar la nueva arquitectura unificada del sistema de recomendaciones para retail.

## Estructura del Plan de Pruebas

El plan de pruebas se organiza en cuatro categorías principales:

1. **Pruebas Unitarias** (`/unit`): Validan componentes individuales de forma aislada
2. **Pruebas de Integración** (`/integration`): Verifican que los componentes funcionan correctamente juntos
3. **Pruebas de Rendimiento** (`/performance`): Evalúan el rendimiento y la escalabilidad del sistema
4. **Datos de Prueba** (`/data`): Proporciona datos compartidos para todas las pruebas

## Configuración del Entorno de Pruebas

Para configurar el entorno de pruebas:

```powershell
# Crear entorno virtual para las pruebas
python -m venv venv.test

# Activar entorno virtual
.\venv.test\Scripts\Activate.ps1

# Instalar dependencias
pip install pytest pytest-asyncio pytest-cov locust
pip install -e .
```

Alternativamente, puede ejecutar el script `run_tests.ps1` que configurará automáticamente el entorno.

## Ejecución de Pruebas

### Usando el Script Automatizado

El script `run_tests.ps1` proporciona una forma sencilla de ejecutar las pruebas:

```powershell
# Ejecutar todas las pruebas (excepto rendimiento)
.\run_tests.ps1

# Ejecutar sólo pruebas unitarias
.\run_tests.ps1 -TestType unit

# Ejecutar sólo pruebas de integración
.\run_tests.ps1 -TestType integration

# Ejecutar pruebas de rendimiento
.\run_tests.ps1 -TestType performance

# Generar informe de cobertura
.\run_tests.ps1 -Coverage

# Salida detallada
.\run_tests.ps1 -Verbose
```

### Ejecución Manual con PyTest

También puede ejecutar las pruebas directamente con PyTest:

```powershell
# Desde el directorio raíz del proyecto
pytest tests/unit -v
pytest tests/integration -v
pytest tests/performance/test_api_performance.py -v
```

### Pruebas de Carga con Locust

Para las pruebas de carga específicas:

```powershell
# Iniciar servidor Locust
locust -f tests/performance/locustfile.py
```

Luego, abra `http://localhost:8089` en su navegador para acceder a la interfaz de Locust.

## Descripción de las Pruebas

### Pruebas Unitarias

| Archivo | Descripción |
|---------|-------------|
| `test_config.py` | Verifica el sistema de configuración centralizado |
| `test_factories.py` | Prueba las fábricas de componentes |
| `test_hybrid_recommender.py` | Valida el recomendador híbrido y la exclusión de productos vistos |
| `test_extensions.py` | Prueba el sistema de extensiones |

### Pruebas de Integración

| Archivo | Descripción |
|---------|-------------|
| `test_api_flow.py` | Verifica los flujos completos end-to-end de la API |
| `test_exclusion.py` | Prueba la funcionalidad de exclusión de productos vistos |

### Pruebas de Rendimiento

| Archivo | Descripción |
|---------|-------------|
| `test_api_performance.py` | Evalúa tiempos de respuesta y uso de recursos |
| `locustfile.py` | Define escenarios de prueba de carga con Locust |

## Estrategia de Validación

1. **Verificación Incremental**: Primero validamos componentes individuales, luego su integración, y finalmente el rendimiento del sistema completo.

2. **Aislamiento de Dependencias**: Utilizamos mocks para aislar componentes y simular servicios externos como Shopify y Google Cloud Retail API.

3. **Cobertura Exhaustiva**: Probamos tanto escenarios exitosos como casos de error y condiciones límite.

4. **Medición de Rendimiento**: Establecemos líneas base para tiempos de respuesta y uso de recursos para detectar regresiones.

## Documentación de Resultados

Después de ejecutar las pruebas con la opción `-Coverage`, se generará un informe de cobertura en el directorio `coverage/`. Este informe muestra qué partes del código están siendo probadas y qué áreas necesitan más pruebas.

Si se ejecuta con la opción `-XmlReport`, se generará un archivo `test-results.xml` que puede ser utilizado por sistemas de integración continua como Jenkins o GitHub Actions.

## Contribución a las Pruebas

Al añadir nuevas funcionalidades, siga estas directrices:

1. **Pruebas Unitarias**: Cree pruebas unitarias para cada nueva clase o función
2. **Pruebas de Integración**: Actualice o cree pruebas de integración para nuevos flujos
3. **Actualize Datos de Prueba**: Mantenga los datos de muestra actualizados y representativos
4. **Pruebas de Rendimiento**: Considere el impacto en el rendimiento y actualice las pruebas según sea necesario

## Problemas Conocidos

- Las pruebas de memoria (usando `memory_profiler`) pueden funcionar de manera diferente en distintos sistemas operativos.
- Para integración completa con Google Cloud Retail API, se requieren credenciales y un proyecto configurado.
