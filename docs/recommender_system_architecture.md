# Arquitectura del Sistema de Recomendaciones para Retail

## Descripción General

Este documento describe la arquitectura completa del Sistema de Recomendaciones para Retail, incluyendo los componentes principales, flujos de datos y decisiones de diseño.

## Versión

**Última actualización:** 12 de abril de 2025  
**Versión de la API:** 0.5.0

## Visión Arquitectónica

El sistema implementa un motor de recomendaciones híbrido para aplicaciones de retail, expuesto como una API REST mediante FastAPI. La arquitectura sigue un diseño modular con clara separación de responsabilidades y mecanismos de fallback robustos.

### Diagrama de Arquitectura

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│    Cliente      │────▶    FastAPI      │────▶  Recomendador   │
│    (Frontend)   │    │  (API Gateway)  │    │     Híbrido     │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       │                                                             │
                       ▼                                                             ▼
          ┌─────────────────────────┐                                   ┌─────────────────────────┐
          │                         │                                   │                         │
          │   TF-IDF Recommender    │                                   │ Google Cloud Retail API │
          │  (Basado en Contenido)  │                                   │(Basado en Comportamiento)│
          │                         │                                   │                         │
          └────────────┬────────────┘                                   └────────────┬────────────┘
                       │                                                             │
                       ▼                                                             ▼
          ┌─────────────────────────┐                                   ┌─────────────────────────┐
          │                         │                                   │                         │
          │    Datos de Productos   │                                   │   Eventos de Usuario    │
          │      (Shopify API)      │                                   │      (Interacciones)    │
          │                         │                                   │                         │
          └─────────────────────────┘                                   └─────────────────────────┘
```

## Componentes Principales

### 1. API REST (FastAPI)

- **Propósito**: Exponer endpoints para recomendaciones, gestión de productos y eventos de usuario
- **Ubicación**: `src/api/main_tfidf_shopify_with_metrics.py`
- **Endpoints Principales**:
  - `/v1/recommendations/{product_id}`: Recomendaciones basadas en producto
  - `/v1/recommendations/user/{user_id}`: Recomendaciones personalizadas
  - `/v1/events/user/{user_id}`: Registro de eventos de usuario
  - `/v1/metrics`: Métricas de rendimiento y calidad
  - `/health`: Verificación de estado del sistema

### 2. Recomendador TF-IDF

- **Propósito**: Generar recomendaciones basadas en similitud de contenido
- **Ubicación**: `src/recommenders/tfidf_recommender.py`
- **Características**:
  - Vectorización TF-IDF de descripciones de productos
  - Cálculo de similitud coseno entre productos
  - Búsqueda de productos por texto
  - Persistencia de modelos entrenados

### 3. Integración con Google Cloud Retail API

- **Propósito**: Proporcionar recomendaciones basadas en comportamiento de usuarios
- **Ubicación**: `src/recommenders/retail_api.py`
- **Características**:
  - Importación de catálogos de productos
  - Registro de eventos de usuario
  - Obtención de recomendaciones personalizadas
  - Procesamiento flexible de respuestas

### 4. Recomendador Híbrido

- **Propósito**: Combinar recomendaciones de diferentes fuentes
- **Ubicación**: Implementado dentro de `main_tfidf_shopify_with_metrics.py`
- **Características**:
  - Ponderación configurable entre fuentes
  - Estrategias de fallback inteligentes
  - Exclusión de productos ya vistos

### 5. Sistema de Métricas

- **Propósito**: Evaluar la calidad y rendimiento de las recomendaciones
- **Ubicación**: `src/api/metrics_router.py` y `src/api/core/metrics.py`
- **Características**:
  - Registro de tiempos de respuesta
  - Conteo de recomendaciones exitosas
  - Análisis de tasas de conversión (si está disponible)

## Flujos Principales

### 1. Inicialización del Sistema

1. **Carga de Configuración**: Variables de entorno y parámetros
2. **Inicialización de Clientes**: Conexión con Shopify y Google Cloud
3. **Carga de Productos**: Desde Shopify o datos de muestra
4. **Entrenamiento del Recomendador**: Vectorización TF-IDF de productos
5. **Importación del Catálogo**: Envío de productos a Google Cloud Retail API

### 2. Flujo de Recomendaciones

#### Basadas en Producto

1. Cliente solicita recomendaciones para un producto específico
2. Se obtienen recomendaciones de TF-IDF (basadas en contenido)
3. Se obtienen recomendaciones de Google Cloud Retail API (basadas en comportamiento)
4. Se combinan y ponderan ambas fuentes
5. Se devuelven las recomendaciones ordenadas por relevancia

#### Personalizadas para Usuario

1. Cliente solicita recomendaciones para un usuario específico
2. Se obtienen recomendaciones de Google Cloud Retail API basadas en historial
3. Se aplican estrategias de fallback si es necesario:
   - Productos populares
   - Productos diversos por categoría
   - Productos similares a los vistos anteriormente
4. Se excluyen productos ya vistos por el usuario
5. Se devuelven las recomendaciones ordenadas por relevancia

### 3. Registro de Eventos de Usuario

1. Cliente registra un evento de usuario (vista, compra, etc.)
2. Se valida el tipo de evento y los parámetros
3. Se procesa el evento según su tipo:
   - Para compras, se añade información de transacción
   - Para vistas, se registra el producto visto
4. Se envía el evento a Google Cloud Retail API
5. Se actualiza el sistema de métricas

## Decisiones de Diseño

### Elección de TF-IDF sobre Transformers

La implementación actual utiliza TF-IDF en lugar de modelos transformer debido a:

1. **Rendimiento**: Tiempos de inicio significativamente más rápidos
2. **Compatibilidad**: Menos problemas de dependencias
3. **Recursos**: Menor consumo de memoria y CPU
4. **Estabilidad**: Mayor fiabilidad en entornos cloud

Los modelos transformer originalmente planeados presentaban:
- Tiempos de inicio excesivos (30-45 segundos)
- Problemas de compatibilidad entre dependencias
- Altos requisitos de recursos

### Arquitectura Híbrida

El sistema utiliza un enfoque híbrido que combina:

1. **Recomendaciones basadas en contenido** (TF-IDF): Para resolver el problema del "cold start"
2. **Recomendaciones basadas en comportamiento** (Google Cloud Retail API): Para personalización

Este enfoque proporciona:
- Mayor relevancia de recomendaciones
- Capacidad para recomendar productos nuevos sin historial
- Personalización basada en comportamiento del usuario

### Manejo de Errores y Resilencia

El sistema implementa estrategias robustas para garantizar la continuidad del servicio:

1. **Fallback en Cascada**: Si una fuente de recomendaciones falla, se utiliza otra
2. **Degradación Elegante**: Funcionalidad reducida en lugar de fallo completo
3. **Timeout y Reintentos**: Para servicios externos con problemas temporales
4. **Modos Offline**: Capacidad de operar con funcionalidad reducida sin servicios externos

### Procesamiento Flexible de Respuestas de API

El sistema ahora implementa un enfoque más flexible para procesar respuestas de API:

1. **Inspección Dinámica**: Examina la estructura real de las respuestas
2. **Extracción Adaptativa**: Soporta diferentes formatos de datos
3. **Valores Predeterminados**: Proporciona valores razonables cuando faltan campos
4. **Logging Detallado**: Facilita el diagnóstico de problemas

## Consideraciones de Despliegue

### Google Cloud Run

El sistema está optimizado para despliegue en Google Cloud Run:

1. **Dockerfile**: Optimizado para reducir tamaño y tiempo de construcción
2. **Health Checks**: Verificación de estado para monitoreo
3. **Variables de Entorno**: Configuración externalizada
4. **Dimensionamiento**: Ajuste de CPU y memoria según necesidades

### Escalabilidad

El sistema está diseñado para escalar según la demanda:

1. **Stateless**: No mantiene estado entre solicitudes
2. **Paralelismo**: Operaciones asíncronas para mejor rendimiento
3. **Caché**: Recomendada para resultados frecuentes
4. **Batch Processing**: Para operaciones con catálogos grandes

## Evolución Futura

El plan de evolución del sistema contempla:

1. **Arquitectura Distribuida**: Separación de componentes en microservicios
2. **Caché Distribuida**: Implementación de Redis para caché
3. **Pre-computación de Embeddings**: Para mejorar rendimiento manteniendo calidad
4. **A/B Testing**: Para evaluar diferentes estrategias de recomendación
5. **Procesamiento Asíncrono de Eventos**: Para mejor rendimiento

## Solución de Problemas Comunes

### Problemas de Inicio

Si la aplicación no inicia correctamente:

1. Verificar logs en startup para identificar errores específicos
2. Comprobar la disponibilidad de credenciales de Google Cloud
3. Verificar la existencia de directorios requeridos (`data/`, `logs/`)

### Problemas con Recomendaciones

Si las recomendaciones no funcionan como se espera:

1. Verificar que el catálogo se ha importado correctamente
2. Comprobar la existencia del producto/usuario solicitado
3. Revisar logs para identificar errores específicos
4. Verificar la estructura de respuesta de Google Cloud Retail API

### Problemas con Eventos de Usuario

Si los eventos no se registran correctamente:

1. Verificar que el tipo de evento es válido
2. Para eventos de compra, asegurar que se proporciona el campo `purchase_amount`
3. Comprobar que los IDs de producto son válidos

## Recursos Adicionales

- [Documentación de FastAPI](https://fastapi.tiangolo.com/)
- [Documentación de Google Cloud Retail API](https://cloud.google.com/retail/docs)
- [Guía de TF-IDF en scikit-learn](https://scikit-learn.org/stable/modules/feature_extraction.html#tfidf-term-weighting)
- [Mejores prácticas para Google Cloud Run](https://cloud.google.com/run/docs/best-practices)
