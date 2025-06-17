idad
    print("🌐 Verificando conectividad...")
    
    # Redis
    if settings.use_redis_cache:
        try:
            import redis.asyncio as redis
            client = await redis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
            await client.ping()
            diagnosis["components"]["redis"] = {"status": "connected"}
            print("✅ Redis: Conectado")
            await client.close()
        except Exception as e:
            diagnosis["components"]["redis"] = {"status": "error", "error": str(e)}
            print(f"❌ Redis: {e}")
    
    # Shopify
    if settings.shopify_shop_url and settings.shopify_access_token:
        try:
            import requests
            url = f"https://{settings.shopify_shop_url}/admin/api/2024-01/shop.json"
            headers = {"X-Shopify-Access-Token": settings.shopify_access_token}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                diagnosis["components"]["shopify"] = {"status": "connected"}
                print("✅ Shopify: Conectado")
            else:
                diagnosis["components"]["shopify"] = {"status": "error", "http_code": response.status_code}
                print(f"❌ Shopify: HTTP {response.status_code}")
        except Exception as e:
            diagnosis["components"]["shopify"] = {"status": "error", "error": str(e)}
            print(f"❌ Shopify: {e}")
    
    # 4. Análisis de rendimiento
    print("⚡ Analizando rendimiento...")
    
    # Memoria
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        diagnosis["performance"]["memory"] = {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "percent": process.memory_percent()
        }
    except:
        pass
    
    # Disco
    try:
        disk_usage = psutil.disk_usage('.')
        diagnosis["performance"]["disk"] = {
            "total_gb": disk_usage.total / 1024 / 1024 / 1024,
            "used_gb": disk_usage.used / 1024 / 1024 / 1024,
            "free_gb": disk_usage.free / 1024 / 1024 / 1024,
            "percent": (disk_usage.used / disk_usage.total) * 100
        }
    except:
        pass
    
    # 5. Generar recomendaciones
    print("💡 Generando recomendaciones...")
    
    # Problemas detectados
    if diagnosis["components"].get("redis", {}).get("status") == "error":
        diagnosis["recommendations"].append({
            "type": "error",
            "component": "redis",
            "message": "Redis no está disponible. El sistema funcionará sin caché.",
            "action": "Verificar configuración de Redis y conectividad de red."
        })
    
    if diagnosis["components"].get("tfidf", {}).get("status") == "model_not_found":
        diagnosis["recommendations"].append({
            "type": "warning",
            "component": "tfidf",
            "message": "Modelo TF-IDF no encontrado.",
            "action": "Ejecutar entrenamiento inicial o copiar modelo pre-entrenado."
        })
    
    if diagnosis.get("performance", {}).get("memory", {}).get("rss_mb", 0) > 1000:
        diagnosis["recommendations"].append({
            "type": "warning",
            "component": "performance",
            "message": f"Alto uso de memoria: {diagnosis['performance']['memory']['rss_mb']:.1f}MB",
            "action": "Considerar optimizar carga de modelos o aumentar recursos."
        })
    
    # Recomendaciones de optimización
    if len(diagnosis["recommendations"]) == 0:
        diagnosis["recommendations"].append({
            "type": "info",
            "component": "system",
            "message": "Sistema funcionando correctamente.",
            "action": "Monitorear métricas de rendimiento periódicamente."
        })
    
    # 6. Guardar reporte
    report_path = f"diagnosis_report_{int(time.time())}.json"
    with open(report_path, 'w') as f:
        json.dump(diagnosis, f, indent=2)
    
    print(f"\n📊 Diagnóstico completado. Reporte guardado en: {report_path}")
    
    # Resumen
    print("\n📈 RESUMEN:")
    total_components = len(diagnosis["components"])
    healthy_components = sum(1 for c in diagnosis["components"].values() if c.get("status") in ["operational", "connected", "configured"])
    
    print(f"• Componentes: {healthy_components}/{total_components} funcionando")
    print(f"• Errores: {sum(1 for r in diagnosis['recommendations'] if r['type'] == 'error')}")
    print(f"• Advertencias: {sum(1 for r in diagnosis['recommendations'] if r['type'] == 'warning')}")
    
    if diagnosis["recommendations"]:
        print("\n🔧 ACCIONES RECOMENDADAS:")
        for i, rec in enumerate(diagnosis["recommendations"], 1):
            icon = "❌" if rec["type"] == "error" else "⚠️" if rec["type"] == "warning" else "💡"
            print(f"{i}. {icon} [{rec['component']}] {rec['message']}")
            print(f"   → {rec['action']}")
    
    return diagnosis

if __name__ == "__main__":
    import time
    asyncio.run(run_comprehensive_diagnosis())
```

---

## 8. Guía de Desarrollo

### 8.1 Configuración del Entorno de Desarrollo

```bash
#!/bin/bash
# setup_dev_environment.sh - Script para configurar entorno de desarrollo

echo "🚀 Configurando entorno de desarrollo para Sistema de Recomendaciones"

# 1. Verificar Python
echo "🐍 Verificando Python..."
python_version=$(python3 --version 2>&1 | grep -o '3\.[0-9]\+')
if [[ $python_version < "3.9" ]]; then
    echo "❌ Se requiere Python 3.9 o superior. Versión actual: $python_version"
    exit 1
fi
echo "✅ Python $python_version detectado"

# 2. Crear entorno virtual
echo "📦 Creando entorno virtual..."
python3 -m venv venv_dev
source venv_dev/bin/activate  # Linux/Mac
# En Windows: venv_dev\Scripts\activate

# 3. Instalar dependencias de desarrollo
echo "📚 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Dependencias de desarrollo

# 4. Configurar pre-commit hooks
echo "🔧 Configurando pre-commit hooks..."
pip install pre-commit
pre-commit install

# 5. Configurar variables de entorno de desarrollo
echo "⚙️ Configurando variables de entorno..."
if [ ! -f .env.dev ]; then
    cp .env.example .env.dev
    echo "📝 Archivo .env.dev creado. Por favor, configura las variables necesarias."
fi

# 6. Crear directorios necesarios
echo "📁 Creando estructura de directorios..."
mkdir -p data logs tests/unit tests/integration tests/performance

# 7. Ejecutar verificaciones iniciales
echo "🔍 Ejecutando verificaciones iniciales..."
python -m pytest tests/unit/ --tb=short
python scripts/verify_setup.py

echo "✅ Entorno de desarrollo configurado correctamente!"
echo "🎯 Próximos pasos:"
echo "   1. Configurar .env.dev con tus credenciales"
echo "   2. Ejecutar: python run.py --dev"
echo "   3. Abrir http://localhost:8000/docs para ver la documentación de la API"
```

### 8.2 Estándares de Código

```python
# standards.py - Estándares de código y mejores prácticas

"""
ESTÁNDARES DE CÓDIGO PARA EL SISTEMA DE RECOMENDACIONES

1. NAMING CONVENTIONS:
   - Clases: PascalCase (ej: TFIDFRecommender)
   - Funciones y variables: snake_case (ej: get_recommendations)
   - Constantes: UPPER_CASE (ej: DEFAULT_CACHE_TTL)
   - Archivos: snake_case (ej: tfidf_recommender.py)

2. DOCSTRINGS:
   - Usar estilo Google para docstrings
   - Documentar todos los métodos públicos
   - Incluir Args, Returns y Raises

3. TYPE HINTS:
   - Usar type hints en todas las funciones públicas
   - Importar tipos de typing module
   - Usar Optional para parámetros opcionales

4. ERROR HANDLING:
   - Usar try/except específicos
   - Logging detallado de errores
   - Degradación elegante donde sea posible

5. ASYNC/AWAIT:
   - Preferir async/await para I/O operations
   - Usar asyncio.gather para operaciones paralelas
   - Manejar excepciones en tasks asíncronos
"""

from typing import List, Dict, Optional, Any, Union
import logging
import asyncio
from datetime import datetime

# Ejemplo de clase que sigue los estándares
class ExampleRecommender:
    """
    Ejemplo de recomendador que sigue los estándares de código.
    
    Esta clase demuestra las mejores prácticas para:
    - Documentación
    - Type hints
    - Manejo de errores
    - Logging
    - Programación asíncrona
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Inicializa el recomendador de ejemplo.
        
        Args:
            config: Configuración del recomendador
            logger: Logger personalizado (opcional)
            
        Raises:
            ValueError: Si la configuración es inválida
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._validate_config()
        
        # Variables privadas con underscore
        self._model_loaded = False
        self._cache: Dict[str, Any] = {}
    
    def _validate_config(self) -> None:
        """
        Valida la configuración del recomendador.
        
        Raises:
            ValueError: Si falta alguna configuración requerida
        """
        required_keys = ['model_path', 'cache_ttl']
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Configuración requerida faltante: {key}")
    
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene recomendaciones para un usuario.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones a devolver
            filters: Filtros adicionales (opcional)
            
        Returns:
            Lista de productos recomendados con formato:
            [
                {
                    "id": "product_123",
                    "title": "Producto ejemplo",
                    "score": 0.95,
                    "metadata": {...}
                }
            ]
            
        Raises:
            ValueError: Si user_id está vacío
            RuntimeError: Si el modelo no está cargado
        """
        # Validación de entrada
        if not user_id or not user_id.strip():
            raise ValueError("user_id no puede estar vacío")
        
        if not self._model_loaded:
            raise RuntimeError("Modelo no está cargado. Llamar load_model() primero.")
        
        # Logging con contexto
        self.logger.info(
            f"Obteniendo recomendaciones para usuario {user_id}",
            extra={
                "user_id": user_id,
                "product_id": product_id,
                "n_recommendations": n_recommendations
            }
        )
        
        try:
            # Simular operación asíncrona
            recommendations = await self._generate_recommendations(
                user_id, product_id, n_recommendations, filters
            )
            
            self.logger.info(f"Generadas {len(recommendations)} recomendaciones para {user_id}")
            return recommendations
            
        except Exception as e:
            self.logger.error(
                f"Error generando recomendaciones para {user_id}: {str(e)}",
                exc_info=True
            )
            # Re-raise con contexto adicional
            raise RuntimeError(f"Fallo generando recomendaciones: {str(e)}") from e
    
    async def _generate_recommendations(
        self,
        user_id: str,
        product_id: Optional[str],
        n_recommendations: int,
        filters: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Genera recomendaciones (método privado).
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto
            n_recommendations: Número de recomendaciones
            filters: Filtros adicionales
            
        Returns:
            Lista de recomendaciones
        """
        # Implementación del algoritmo
        # Usar await para operaciones I/O
        await asyncio.sleep(0.1)  # Simular cálculo
        
        # Retornar datos estructurados
        return [
            {
                "id": f"product_{i}",
                "title": f"Producto {i}",
                "score": 0.9 - (i * 0.1),
                "metadata": {
                    "algorithm": "example",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            for i in range(n_recommendations)
        ]
    
    async def load_model(self) -> bool:
        """
        Carga el modelo de recomendación.
        
        Returns:
            True si la carga fue exitosa, False en caso contrario
        """
        try:
            # Simular carga de modelo
            await asyncio.sleep(0.5)
            self._model_loaded = True
            self.logger.info("Modelo cargado exitosamente")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cargando modelo: {str(e)}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del recomendador.
        
        Returns:
            Diccionario con información de estado
        """
        return {
            "status": "healthy" if self._model_loaded else "degraded",
            "model_loaded": self._model_loaded,
            "cache_size": len(self._cache),
            "timestamp": datetime.utcnow().isoformat()
        }
```

### 8.3 Testing Guidelines

```python
# test_example.py - Ejemplo de tests siguiendo mejores prácticas

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.recommenders.example_recommender import ExampleRecommender

class TestExampleRecommender:
    """
    Test suite para ExampleRecommender.
    
    Demuestra mejores prácticas para testing:
    - Fixtures para setup/teardown
    - Mocking de dependencias externas
    - Tests de casos edge
    - Tests asíncronos
    """
    
    @pytest.fixture
    def mock_logger(self):
        """Fixture para logger mock."""
        return Mock()
    
    @pytest.fixture
    def valid_config(self):
        """Fixture para configuración válida."""
        return {
            "model_path": "/path/to/model",
            "cache_ttl": 3600
        }
    
    @pytest.fixture
    def recommender(self, valid_config, mock_logger):
        """Fixture para instancia de recomendador."""
        return ExampleRecommender(valid_config, mock_logger)
    
    def test_init_valid_config(self, valid_config, mock_logger):
        """Test inicialización con configuración válida."""
        recommender = ExampleRecommender(valid_config, mock_logger)
        assert recommender.config == valid_config
        assert recommender.logger == mock_logger
        assert not recommender._model_loaded
    
    def test_init_invalid_config(self, mock_logger):
        """Test inicialización con configuración inválida."""
        invalid_config = {"missing_required": "value"}
        
        with pytest.raises(ValueError, match="Configuración requerida faltante"):
            ExampleRecommender(invalid_config, mock_logger)
    
    @pytest.mark.asyncio
    async def test_get_recommendations_success(self, recommender):
        """Test obtención exitosa de recomendaciones."""
        # Setup
        recommender._model_loaded = True
        
        # Execute
        result = await recommender.get_recommendations("user_123", n_recommendations=3)
        
        # Verify
        assert len(result) == 3
        assert all("id" in rec for rec in result)
        assert all("score" in rec for rec in result)
        assert result[0]["score"] > result[1]["score"]  # Ordenado por score
    
    @pytest.mark.asyncio
    async def test_get_recommendations_empty_user_id(self, recommender):
        """Test con user_id vacío."""
        recommender._model_loaded = True
        
        with pytest.raises(ValueError, match="user_id no puede estar vacío"):
            await recommender.get_recommendations("")
    
    @pytest.mark.asyncio
    async def test_get_recommendations_model_not_loaded(self, recommender):
        """Test con modelo no cargado."""
        with pytest.raises(RuntimeError, match="Modelo no está cargado"):
            await recommender.get_recommendations("user_123")
    
    @pytest.mark.asyncio
    async def test_load_model_success(self, recommender):
        """Test carga exitosa de modelo."""
        result = await recommender.load_model()
        
        assert result is True
        assert recommender._model_loaded is True
    
    @pytest.mark.asyncio
    async def test_load_model_failure(self, recommender):
        """Test fallo en carga de modelo."""
        # Mock para simular error
        with patch.object(recommender, '_model_loaded', side_effect=Exception("Mock error")):
            result = await recommender.load_model()
            
            assert result is False
    
    def test_health_check_model_loaded(self, recommender):
        """Test health check con modelo cargado."""
        recommender._model_loaded = True
        
        result = recommender.health_check()
        
        assert result["status"] == "healthy"
        assert result["model_loaded"] is True
        assert "timestamp" in result
    
    def test_health_check_model_not_loaded(self, recommender):
        """Test health check con modelo no cargado."""
        result = recommender.health_check()
        
        assert result["status"] == "degraded"
        assert result["model_loaded"] is False

# Ejemplo de test de integración
class TestRecommenderIntegration:
    """Tests de integración para el sistema completo."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_recommendation_flow(self):
        """Test del flujo completo de recomendación."""
        # Este test requiere servicios externos funcionando
        # Marcar con @pytest.mark.integration para ejecutar separadamente
        pass
    
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_recommendation_performance(self):
        """Test de rendimiento de recomendaciones."""
        import time
        
        recommender = ExampleRecommender({
            "model_path": "/path/to/model",
            "cache_ttl": 3600
        })
        
        await recommender.load_model()
        
        # Medir tiempo de 100 recomendaciones
        start_time = time.time()
        
        tasks = [
            recommender.get_recommendations(f"user_{i}")
            for i in range(100)
        ]
        
        await asyncio.gather(*tasks)
        
        duration = time.time() - start_time
        avg_time = duration / 100
        
        # Assertion de rendimiento
        assert avg_time < 0.1, f"Promedio de {avg_time:.3f}s por recomendación es muy lento"

# Configuración de pytest
# pytest.ini
"""
[tool:pytest]
minversion = 6.0
addopts = 
    -ra 
    -q 
    --tb=short
    --strict-markers
    --disable-warnings
testpaths = tests
markers =
    unit: Unit tests
    integration: Integration tests 
    performance: Performance tests
    slow: Slow tests
asyncio_mode = auto

[tool:coverage:run]
source = src
omit = 
    */tests/*
    */venv/*
    setup.py

[tool:coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
"""
```

### 8.4 Workflow de Desarrollo

```python
# development_workflow.py - Guía del workflow de desarrollo

"""
WORKFLOW DE DESARROLLO

1. PREPARACIÓN:
   - Crear rama desde main: git checkout -b feature/nueva-funcionalidad
   - Actualizar dependencias: pip install -r requirements.txt
   - Ejecutar tests: pytest tests/unit/

2. DESARROLLO:
   - Escribir tests primero (TDD)
   - Implementar funcionalidad
   - Ejecutar tests frecuentemente
   - Usar pre-commit hooks

3. TESTING:
   - Tests unitarios: pytest tests/unit/
   - Tests de integración: pytest tests/integration/ -m integration
   - Tests de rendimiento: pytest tests/performance/ -m performance
   - Cobertura: pytest --cov=src tests/

4. DOCUMENTACIÓN:
   - Actualizar docstrings
   - Actualizar README si es necesario
   - Documentar cambios de API

5. REVISIÓN:
   - Lint: flake8 src/
   - Type checking: mypy src/
   - Security: bandit -r src/
   - Formateo: black src/ tests/

6. COMMIT Y PUSH:
   - Commits atómicos con mensajes descriptivos
   - Push de rama: git push origin feature/nueva-funcionalidad
   - Crear Pull Request

7. DEPLOYMENT:
   - Tests pasan en CI/CD
   - Revisión de código aprobada
   - Merge a main
   - Deploy automático a staging
   - Validación en staging
   - Deploy a production
"""

# Scripts útiles para desarrollo
import subprocess
import sys
from pathlib import Path

def run_all_checks():
    """Ejecuta todas las verificaciones de calidad de código."""
    
    print("🔍 Ejecutando verificaciones de calidad...")
    
    checks = [
        ("Linting", ["flake8", "src/", "tests/"]),
        ("Type Checking", ["mypy", "src/"]),
        ("Security", ["bandit", "-r", "src/"]),
        ("Tests Unitarios", ["pytest", "tests/unit/", "-v"]),
        ("Cobertura", ["pytest", "--cov=src", "tests/", "--cov-report=term-missing"])
    ]
    
    results = []
    
    for name, cmd in checks:
        print(f"\n🔧 {name}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ {name}: PASSED")
            results.append((name, True, ""))
        except subprocess.CalledProcessError as e:
            print(f"❌ {name}: FAILED")
            print(f"Error: {e.stdout}\n{e.stderr}")
            results.append((name, False, e.stderr))
    
    # Resumen
    print("\n📊 RESUMEN:")
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    print(f"Verificaciones: {passed}/{total} pasaron")
    
    if passed == total:
        print("✅ Todas las verificaciones pasaron. Listo para commit!")
        return True
    else:
        print("❌ Algunas verificaciones fallaron. Revisar errores arriba.")
        return False

def setup_pre_commit():
    """Configura pre-commit hooks."""
    
    pre_commit_config = """
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        additional_dependencies: [flake8-docstrings]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
"""
    
    with open(".pre-commit-config.yaml", "w") as f:
        f.write(pre_commit_config)
    
    # Instalar hooks
    subprocess.run(["pre-commit", "install"], check=True)
    print("✅ Pre-commit hooks configurados")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        run_all_checks()
    elif len(sys.argv) > 1 and sys.argv[1] == "setup-hooks":
        setup_pre_commit()
    else:
        print("Uso: python development_workflow.py [check|setup-hooks]")
```

---

## 9. Conclusión

Esta documentación técnica profunda proporciona una guía completa para entender, desarrollar y mantener el Sistema de Recomendaciones para Retail. Los componentes clave incluyen:

### Aspectos Destacados:

1. **Arquitectura Multicapa** con separación clara de responsabilidades
2. **Sistema de Caché Híbrido** con 5 niveles de fallback para máxima resiliencia
3. **Patrones de Diseño Avanzados** (Factory, Strategy, Circuit Breaker, Observer)
4. **Observabilidad Completa** con métricas, logging estructurado y alertas
5. **Herramientas de Diagnóstico** automatizadas para troubleshooting
6. **Estándares de Desarrollo** rigurosos con testing comprehensivo

### Próximos Pasos:

1. **Revisar y aplicar** los estándares de código a módulos existentes
2. **Implementar** el sistema de métricas avanzado
3. **Configurar** las herramientas de monitoreo y alertas
4. **Expandir** la suite de tests con casos de integración y rendimiento
5. **Documentar** procedimientos operacionales específicos

Esta documentación servirá como referencia técnica definitiva para el equipo de desarrollo y facilitará la incorporación de nuevos miembros al proyecto.

---

**Versión**: 1.0  
**Fecha**: 25 de mayo de 2025  
**Autor**: Equipo de Arquitectura del Sistema de Recomendaciones