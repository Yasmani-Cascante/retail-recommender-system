# Sistema de Recomendaciones para Retail - Nivel Empresarial

[![Estado](https://img.shields.io/badge/Estado-Producción%20Empresarial-success)](https://github.com)
[![Versión](https://img.shields.io/badge/Versión-0.5.0-blue)](https://github.com)
[![Python](https://img.shields.io/badge/Python-3.9+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com)
[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Ready-orange)](https://cloud.google.com)

## 🏆 Sistema de Recomendaciones Híbrido de Nivel Empresarial

Este es un **sistema de recomendaciones completamente funcional y desplegado en producción** que combina algoritmos de machine learning avanzados con integración de servicios cloud empresariales para ofrecer recomendaciones personalizadas de alta calidad en aplicaciones de retail.

### ⭐ Características Empresariales

- 🤖 **Sistema de Recomendaciones Híbrido**: Combina TF-IDF con Google Cloud Retail API
- ⚡ **Sistema de Caché Híbrido con Redis**: 5 niveles de fallback con resiliencia empresarial
- 🔒 **Validación Inteligente de Productos**: Resumen automático de descripciones largas
- 📊 **Sistema de Métricas en Tiempo Real**: Monitoreo empresarial completo
- 🏗️ **Arquitectura Modular**: Patrón de fábricas con configuración centralizada
- 🛡️ **Resiliencia y Tolerancia a Fallos**: Degradación elegante ante fallos
- 🚀 **Despliegue Automatizado**: Scripts DevOps para múltiples entornos
- 🧪 **Suite de Pruebas Comprehensiva**: Unitarias, integración y rendimiento

## 🏗️ Arquitectura del Sistema

### Componentes Principales

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│    Cliente      │────▶    FastAPI      │────▶  Recomendador   │
│   (Frontend)    │    │  (API Gateway)  │    │     Híbrido     │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                      │
                ┌─────────────────────────────────────┴─────────────────────────────────────┐
                │                                                                           │
                ▼                                                                           ▼
    ┌─────────────────────────┐                                               ┌─────────────────────────┐
    │                         │                                               │                         │
    │   TF-IDF Recommender    │                                               │ Google Cloud Retail API │
    │  (Basado en Contenido)  │                                               │(Basado en Comportamiento)│
    │                         │                                               │                         │
    └────────────┬────────────┘                                               └────────────┬────────────┘
                 │                                                                         │
                 ▼                                                                         ▼
    ┌─────────────────────────┐          ┌─────────────────────────┐          ┌─────────────────────────┐
    │                         │          │                         │          │                         │
    │   Sistema de Caché      │          │    Datos de Productos   │          │   Eventos de Usuario    │
    │   Híbrido (Redis)       │◄────────▶│      (Shopify API)      │          │      (Interacciones)    │
    │   • 5 Niveles Fallback  │          │                         │          │                         │
    └─────────────────────────┘          └─────────────────────────┘          └─────────────────────────┘
```

### Flujo de Datos de Alto Nivel

1. **Ingesta de Datos**: Shopify → Validación → Google Cloud Retail API
2. **Procesamiento**: TF-IDF + Retail API → Recomendador Híbrido
3. **Caché Inteligente**: Redis → Local → Shopify → Gateway → Producto Mínimo
4. **Respuesta**: JSON enriquecido con métricas de rendimiento

## 🚀 Instalación y Configuración

### Prerrequisitos

- **Python 3.9+** (Recomendado: 3.11)
- **Google Cloud SDK** con proyecto configurado
- **Redis** (Local o Google Cloud Memorystore)
- **Cuenta Shopify** con API access token

### Instalación Rápida

```bash
# 1. Clonar repositorio
git clone https://github.com/tu-usuario/retail-recommender-system.git
cd retail-recommender-system

# 2. Crear entorno virtual
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux/Mac  
source venv/bin/activate

# 3. Instalar dependencias (corregido para Pydantic v2)
pip install -r requirements.txt
pip install pydantic-settings  # Corrección para BaseSettings

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus configuraciones reales

# 5. Verificar instalación
python verify_cache_system_fixed.py
```

### Configuración de Variables de Entorno

Crea un archivo `.env` con la siguiente configuración:

```bash
# === CONFIGURACIÓN PRINCIPAL ===
GOOGLE_PROJECT_NUMBER=tu_numero_proyecto
GOOGLE_LOCATION=global
GOOGLE_CATALOG=default_catalog
GOOGLE_SERVING_CONFIG=default_recommendation_config
API_KEY=tu_api_key_segura

# === SHOPIFY INTEGRATION ===
SHOPIFY_SHOP_URL=tu-tienda.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_tu_token_acceso

# === REDIS CACHE SYSTEM ===
USE_REDIS_CACHE=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_SSL=false
CACHE_TTL=86400
CACHE_PREFIX=product:
CACHE_ENABLE_BACKGROUND_TASKS=true

# === GOOGLE CLOUD STORAGE ===
GCS_BUCKET_NAME=tu-bucket-gcs
USE_GCS_IMPORT=true

# === CARACTERÍSTICAS AVANZADAS ===
DEBUG=false
METRICS_ENABLED=true
EXCLUDE_SEEN_PRODUCTS=true
DEFAULT_CURRENCY=COP
STARTUP_TIMEOUT=300.0
```

## 🎯 Funcionalidades Principales

### 1. Sistema de Recomendaciones Híbrido ⭐⭐⭐⭐⭐

#### Algoritmo TF-IDF Optimizado
- **Vectorización avanzada**: 5000 características con unigramas y bigramas
- **Búsqueda semántica**: Similitud coseno para productos relacionados
- **Persistencia de modelos**: Carga/guardado automático de modelos entrenados
- **Búsqueda de texto**: Búsqueda por similitud en descripciones

#### Integración Google Cloud Retail API
- **Doble importación**: Directa (<50 productos) y vía GCS (>50 productos)
- **Eventos de usuario**: 6 tipos de eventos con validación automática
- **Transacciones de compra**: Soporte completo para ISO 4217 (monedas)
- **Gestión de catálogos**: Creación automática de ramas y configuraciones

### 2. Sistema de Caché Híbrido Avanzado ⭐⭐⭐⭐⭐

El sistema implementa un mecanismo de caché híbrido que utiliza Redis para optimizar el rendimiento y resolver el problema de enriquecimiento de productos que no existen en el catálogo local:

### Características del Sistema de Caché

- **Caché centralizada con Redis**: Proporciona almacenamiento en caché rápido y distribuido
- **Múltiples niveles de fallback**: Redis -> Catálogo local -> Shopify -> Gateway -> Producto mínimo
- **Estadisticas y monitoreo**: Seguimiento de hit ratio, éxitos y fallos
- **Invalidación de caché**: Soporte para invalidar productos individuales o grupos
- **Precarga de productos**: Optimización para cargar múltiples productos en paralelo
- **Resiliencia ante fallos**: Degradación elegante cuando Redis no está disponible

### Activación del Sistema de Caché

Para activar el sistema de caché, configura las siguientes variables de entorno:

```
USE_REDIS_CACHE=true
REDIS_HOST=localhost  # O la dirección del servidor Redis
REDIS_PORT=6379
```

Para desplegar con caché en Google Cloud:

```powershell
# Crear instancia de Redis en Google Cloud Memorystore
.\create_redis.ps1

# Desplegar versión con caché
.\deploy_cached.ps1
```


```python
# Arquitectura de 5 niveles de fallback
Redis Cache (Nivel 1) 
    ↓ (Miss)
Catálogo Local (Nivel 2)
    ↓ (Miss)  
Shopify API (Nivel 3)
    ↓ (Miss)
Gateway Externo (Nivel 4)
    ↓ (Miss)
Producto Mínimo (Nivel 5)
```

**Características avanzadas**:
- **Hit Ratio Tracking**: Métricas en tiempo real de rendimiento
- **Health Checks Automáticos**: Monitoreo cada 5 minutos
- **Precarga Inteligente**: Optimización para consultas masivas
- **Invalidación Selectiva**: Individual y en lotes
- **Degradación Elegante**: Funciona sin Redis

### 3. Validación Inteligente de Productos ⭐⭐⭐⭐⭐

```python
class ProductValidator:
    def _summarize_description(self, description: str):
        # Algoritmo proprietario de resumen inteligente:
        # 1. Análisis de oraciones por importancia
        # 2. Ponderación por posición y palabras clave  
        # 3. Optimización para límite de 5000 caracteres
        # 4. Preservación del contexto semántico
```

**Innovaciones**:
- **Resumen Semántico**: No trunca, preserva información clave
- **Validación Multi-campo**: Títulos, descripciones, precios, categorías
- **Logging de Auditoría**: Registro completo de modificaciones
- **Estadísticas de Calidad**: Métricas de validación por lote

### 4. Sistema de Métricas Empresarial ⭐⭐⭐⭐⭐

```python
# Métricas disponibles en /v1/metrics
{
    "realtime_metrics": {
        "total_requests": 15420,
        "average_response_time_ms": 127.3,
        "p95_response_time_ms": 285.1,
        "fallback_rate": 0.12,
        "cache_hit_ratio": 0.87
    },
    "business_metrics": {
        "recommendations_by_source": {
            "content_based": 45.2,
            "collaborative": 54.8
        },
        "user_interactions": {
            "detail_page_views": 8234,
            "add_to_cart": 1847,
            "purchases": 423
        }
    }
}
```

## 🔧 Opciones de Despliegue

### Desarrollo Local

```bash
# Desarrollo con recarga automática
uvicorn src.api.main_tfidf_shopify_with_metrics:app --reload --port 8000

# O usar el script de desarrollo
python run.py
```

### Producción en Google Cloud Run

```powershell
# Despliegue automatizado con todas las optimizaciones
.\deploy_tfidf_metrics.ps1

# Despliegue de arquitectura unificada (recomendado)
.\deploy_unified.ps1

# Despliegue con caché Redis optimizado
.\deploy_cached.ps1
```

### Docker Local

```bash
# Construir imagen optimizada
docker build -t retail-recommender -f Dockerfile.tfidf.shopify.improved .

# Ejecutar con variables de entorno
docker run -p 8080:8080 --env-file .env retail-recommender
```

## 📊 Endpoints de la API

### Endpoints Principales

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| GET | `/v1/recommendations/{product_id}` | Recomendaciones basadas en producto | ✅ |
| GET | `/v1/recommendations/user/{user_id}` | Recomendaciones personalizadas | ✅ |
| POST | `/v1/events/user/{user_id}` | Registro de eventos de usuario | ✅ |
| GET | `/v1/products/` | Lista productos (paginado) | ❌ |
| GET | `/v1/products/search/` | Búsqueda semántica | ✅ |
| GET | `/v1/metrics` | Métricas del sistema | ✅ |
| GET | `/health` | Estado del sistema + caché | ❌ |

### Ejemplos de Uso

```bash
# Headers requeridos para endpoints autenticados
export API_KEY="tu_api_key"
export BASE_URL="https://tu-servicio.run.app"

# 1. Registrar evento de vista de producto
curl -X POST "$BASE_URL/v1/events/user/usuario123?event_type=detail-page-view&product_id=prod456" \
  -H "X-API-Key: $API_KEY"

# 2. Obtener recomendaciones personalizadas (excluye productos vistos)
curl "$BASE_URL/v1/recommendations/user/usuario123?n=10" \
  -H "X-API-Key: $API_KEY"

# 3. Búsqueda semántica de productos
curl "$BASE_URL/v1/products/search/?q=camiseta+algodón+azul" \
  -H "X-API-Key: $API_KEY"

# 4. Métricas en tiempo real
curl "$BASE_URL/v1/metrics" \
  -H "X-API-Key: $API_KEY"
```

## 🧪 Testing y Validación

### Suite de Pruebas Empresarial

```bash
# Pruebas unitarias completas
pytest tests/unit/ -v --cov=src

# Pruebas de integración end-to-end  
pytest tests/integration/ -v

# Pruebas de rendimiento con Locust
locust -f tests/performance/locustfile.py

# Verificación del sistema de caché
python verify_cache_system_fixed.py

# Suite completa automatizada
.\run_tests.ps1 -Coverage -Verbose
```

### Tipos de Pruebas

| Tipo | Descripción | Cobertura |
|------|-------------|-----------|
| **Unitarias** | Componentes aislados | 85%+ |
| **Integración** | Flujos end-to-end | 90%+ |
| **Rendimiento** | Carga y estrés | SLA definido |
| **Redis** | Conectividad y operaciones | 100% |
| **API** | Todos los endpoints | 100% |

## 📈 Monitoreo y Observabilidad

### Métricas de Rendimiento

- **Tiempo de respuesta**: P50, P95, P99
- **Throughput**: Requests per second
- **Tasa de error**: Errores 4xx/5xx
- **Cache hit ratio**: Eficiencia del caché Redis
- **Fallback usage**: Uso de estrategias de respaldo

### Logs Estructurados

```json
{
  "timestamp": "2025-05-22T01:37:42.912Z",
  "level": "INFO",
  "logger": "src.api.core.product_cache",
  "message": "Cache hit: producto 123 obtenido de Redis",
  "metadata": {
    "user_id": "user_456",
    "product_id": "123",
    "cache_source": "redis",
    "response_time_ms": 12.3
  }
}
```

### Health Checks

```bash
# Estado del sistema completo
curl https://tu-servicio.run.app/health

# Respuesta típica
{
  "status": "operational",
  "components": {
    "recommender": {
      "status": "operational",
      "products_count": 15420,
      "loaded": true
    },
    "cache": {
      "status": "operational", 
      "redis_connection": "connected",
      "hit_ratio": 0.87,
      "stats": {...}
    }
  },
  "uptime_seconds": 86400
}
```

## 🔒 Seguridad Empresarial

### Autenticación y Autorización

- **API Key Authentication**: Header `X-API-Key`
- **Rate Limiting**: Configurable por endpoint
- **CORS**: Configurado para dominios específicos
- **Input Validation**: Pydantic schemas en todos los endpoints

### Buenas Prácticas

- **Secretos externalizados**: Variables de entorno
- **Logs sin secretos**: Redacción automática de información sensible
- **HTTPS obligatorio**: En todos los entornos de producción
- **Auditoría completa**: Logs de todas las operaciones

## 🛠️ Mantenimiento y Operaciones

### Tareas de Mantenimiento

```bash
# Actualizar catálogo de productos
python scripts/update_catalog.py

# Limpiar caché Redis
python scripts/cache_maintenance.py --clean

# Exportar métricas históricas  
python scripts/export_metrics.py --days 30

# Verificar salud del sistema
python verify_cache_system_fixed.py
```

### Troubleshooting Común

| Problema | Síntoma | Solución |
|----------|---------|----------|
| **Caché lento** | Hit ratio < 50% | Verificar Redis, ajustar TTL |
| **Recomendaciones vacías** | Array vacío | Verificar catálogo Shopify |
| **Eventos fallando** | Error 500 en POST | Verificar Google Retail API |
| **Alta latencia** | P95 > 500ms | Escalar instancias Cloud Run |

## 🚀 Roadmap y Mejoras Futuras

### Corto Plazo (1-2 meses)
- [ ] **Consolidación arquitectura unificada**: Migración completa
- [ ] **CI/CD pipeline**: GitHub Actions automated
- [ ] **Dashboards Grafana**: Visualización avanzada de métricas
- [ ] **A/B Testing**: Framework para experimentos

### Mediano Plazo (3-6 meses)  
- [ ] **Frontend administrativo**: React dashboard
- [ ] **ML Pipeline automation**: Reentrenamiento automático
- [ ] **Multi-tenant support**: Soporte para múltiples clientes
- [ ] **Edge deployment**: CDN para latencia global

### Largo Plazo (6+ meses)
- [ ] **Deep Learning models**: Transformers en producción
- [ ] **Real-time personalization**: Personalización en tiempo real  
- [ ] **Advanced analytics**: Análisis predictivo de tendencias
- [ ] **Mobile SDK**: SDKs nativos para iOS/Android

## 👥 Contribución

### Proceso de Contribución

1. **Fork** del repositorio
2. **Crear rama**: `git checkout -b feature/nueva-funcionalidad`
3. **Implementar**: Seguir estándares de código
4. **Tests**: Añadir pruebas comprehensivas
5. **Documentar**: Actualizar README y docs/
6. **Pull Request**: Descripción detallada de cambios

### Estándares de Código

- **PEP 8**: Estilo de código Python
- **Type hints**: Tipado estático en funciones
- **Docstrings**: Documentación en español
- **Test coverage**: Mínimo 80% de cobertura
- **Security review**: Revisión de seguridad obligatoria

## 📞 Soporte y Contacto

### Canales de Soporte

- **Documentación**: [docs/](docs/) (Técnica detallada)
- **Issues**: GitHub Issues para bugs y features
- **Discussions**: GitHub Discussions para preguntas
- **Email**: soporte@retail-recommender.com

### SLA de Soporte

- **Bugs críticos**: < 4 horas
- **Bugs menores**: < 48 horas  
- **Feature requests**: < 1 semana
- **Documentación**: < 72 horas

## 📄 Licencia

Este proyecto está licenciado bajo la **Licencia MIT** - ver el archivo [LICENSE](LICENSE) para detalles.

---

## ⚡ Quick Start Guide

```bash
# 1-liner para empezar
git clone https://github.com/tu-usuario/retail-recommender-system.git && cd retail-recommender-system && python -m venv venv && .\venv\Scripts\activate && pip install -r requirements.txt pydantic-settings && cp .env.example .env && echo "✅ Sistema listo! Edita .env y ejecuta: python run.py"
```

---

**🏆 Sistema de Recomendaciones de Nivel Empresarial - Desplegado en Producción**

*Desarrollado con ❤️ para revolucionar la experiencia de recomendaciones en retail*