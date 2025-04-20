# Pruebas Unitarias para el Sistema de Recomendaciones

Este directorio contiene las pruebas unitarias para los componentes principales del sistema de recomendaciones con arquitectura unificada.

## Estructura

- `test_config.py`: Pruebas para el sistema de configuración centralizado
- `test_factories.py`: Pruebas para las fábricas de componentes
- `test_hybrid_recommender.py`: Pruebas para el recomendador híbrido
- `test_extensions.py`: Pruebas para el sistema de extensiones

## Ejecución de Pruebas

### Requisitos

Antes de ejecutar las pruebas, asegúrese de tener instaladas las dependencias necesarias:

```bash
pip install pytest pytest-asyncio
```

### Comandos

Para ejecutar todas las pruebas unitarias:

```bash
pytest tests/unit -v
```

Para ejecutar un archivo de pruebas específico:

```bash
pytest tests/unit/test_config.py -v
```

Para ejecutar una prueba específica:

```bash
pytest tests/unit/test_config.py::test_config_default_values -v
```

### Opciones Útiles

- `-v`: Modo verboso, muestra más detalles
- `-s`: Muestra la salida de print() durante las pruebas
- `--tb=short`: Muestra trazas de error más compactas
- `-k "nombre"`: Ejecuta solo pruebas que coincidan con el patrón de nombre

## Creación de Nuevas Pruebas

Al crear nuevas pruebas unitarias, siga estas convenciones:

1. Prefije los nombres de los archivos con `test_`
2. Prefije los nombres de las funciones de prueba con `test_`
3. Use fixtures de pytest para reutilizar objetos de prueba
4. Use mocks para simular dependencias externas
5. Para pruebas asíncronas, use el decorador `@pytest.mark.asyncio`

Ejemplo:

```python
import pytest

@pytest.fixture
def sample_data():
    return {"key": "value"}

def test_simple_function(sample_data):
    assert "key" in sample_data

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

## Mejores Prácticas

- Mantenga las pruebas independientes entre sí
- Limpie los recursos después de cada prueba
- Pruebe tanto los casos exitosos como los casos de error
- Use fixtures parametrizados para probar múltiples escenarios
- Documente el propósito de cada prueba con buenos docstrings
