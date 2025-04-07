# Instrucciones para Implementar el Sistema de Métricas

Este documento proporciona instrucciones paso a paso para implementar y probar el sistema de métricas en la API de recomendaciones.

## Opción 1: Despliegue Rápido (Solo Endpoint de Métricas)

Si solo quieres probar el endpoint de métricas sin modificar la aplicación principal:

1. Ejecuta el script de despliegue rápido:
   ```powershell
   .\deploy_metrics.ps1
   ```

2. Este script:
   - Crea un Dockerfile temporal específico para métricas
   - Despliega una versión simplificada de la API que solo incluye el endpoint de métricas
   - Proporciona instrucciones para probar el endpoint

3. Probando el endpoint:
   ```
   GET https://retail-recommender-metrics-178362262166.us-central1.run.app/v1/metrics
   ```
   (Incluye el header `X-API-Key: 2fed9999056fab6dac5654238f0cae1c`)

## Opción 2: Despliegue Completo (Sistema Completo con Métricas)

Para integrar las métricas en el sistema completo de recomendaciones:

1. Ejecuta el script de despliegue completo:
   ```powershell
   .\deploy_tfidf_full_metrics.ps1
   ```

2. Este script:
   - Modifica el archivo principal para incluir el router de métricas
   - Crea un Dockerfile temporal que usa este archivo modificado
   - Despliega la versión completa del sistema con todas las funcionalidades:
     - Sistema de recomendaciones TF-IDF
     - Conexión a Shopify
     - Exclusión de productos vistos
     - Sistema de métricas

3. Probando todas las funcionalidades:
   ```
   # Verificar métricas
   GET https://retail-recommender-full-metrics-178362262166.us-central1.run.app/v1/metrics

   # Registrar un evento
   POST https://retail-recommender-full-metrics-178362262166.us-central1.run.app/v1/events/user/test_user_456?event_type=detail-page-view&product_id=9978503037237

   # Obtener recomendaciones (excluyendo productos vistos)
   GET https://retail-recommender-full-metrics-178362262166.us-central1.run.app/v1/recommendations/user/test_user_456
   ```
   (Incluye el header `X-API-Key: 2fed9999056fab6dac5654238f0cae1c` en todas las solicitudes)

## Entendiendo el Sistema de Métricas

El sistema de métricas proporciona:

1. **Métricas de Recomendaciones**:
   - Tipos de recomendaciones generadas
   - Tiempo de respuesta
   - Tasa de fallback
   - Diversidad de categorías en las recomendaciones
   - Novedad de las recomendaciones (productos no mostrados anteriormente)

2. **Métricas de Interacción**:
   - Eventos de usuario registrados
   - Conversiones de recomendaciones (interacciones con productos recomendados)
   - Distribución de tipos de eventos

3. **Estadísticas Generales**:
   - Número total de solicitudes procesadas
   - Tiempo de respuesta promedio y máximo
   - Distribución de tipos de recomendación

## Ejemplo de Respuesta del Endpoint de Métricas

```json
{
  "status": "success",
  "realtime_metrics": {
    "total_requests": 25,
    "average_response_time_ms": 245.32,
    "max_response_time_ms": 532.67,
    "recommendation_type_distribution": {
      "personalized_fallback": 0.35,
      "diverse_fallback": 0.15,
      "popular_fallback": 0.5
    },
    "top_10_category_distribution": {
      "AROS": 0.42,
      "LENCERIA": 0.25,
      "AROMAS": 0.18,
      "ROPA": 0.15
    },
    "fallback_rate": 1.0
  },
  "timestamp": "2025-04-08T12:34:56"
}
```

## Mejoras Adicionales Implementadas

Además del sistema de métricas, se han implementado otras mejoras importantes:

1. **Exclusión de Productos Vistos**:
   - Las recomendaciones ahora excluyen automáticamente productos con los que el usuario ya ha interactuado
   - Se implementa mediante el filtrado de productos basado en los eventos de usuario
   - Esta funcionalidad mejora la experiencia del usuario al mostrar siempre contenido nuevo

2. **Tracking de Recomendaciones**:
   - Ahora se puede incluir el parámetro `recommendation_id` al registrar eventos
   - Esto permite realizar un seguimiento de qué recomendaciones conducen a interacciones
   - Útil para evaluar la efectividad de diferentes estrategias de recomendación

## Configuración

El sistema de métricas puede habilitarse o deshabilitarse mediante la variable de entorno `METRICS_ENABLED`:

- `METRICS_ENABLED=true`: Habilita la recopilación y consulta de métricas (valor predeterminado)
- `METRICS_ENABLED=false`: Deshabilita la recopilación y consulta de métricas

Las métricas se almacenan en memoria durante la ejecución del servicio y opcionalmente se pueden guardar en archivos para análisis histórico.

## Próximos Pasos

Para avanzar con el sistema de métricas en el futuro:

1. **Implementar Almacenamiento Persistente**:
   - Configurar una base de datos (como BigQuery) para almacenar métricas a largo plazo
   - Permitir análisis histórico y tendencias a lo largo del tiempo

2. **Dashboard de Visualización**:
   - Crear un panel de control para visualizar métricas clave
   - Implementar alertas para problemas de rendimiento

3. **Pruebas A/B**:
   - Utilizar métricas para comparar diferentes estrategias de recomendación
   - Implementar un sistema formal de pruebas A/B
