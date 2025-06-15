# Corrección Crítica: Recomendador Híbrido No Incluye Retail API

## 🚨 Problema Identificado

La versión unificada del sistema de recomendaciones no está incluyendo las recomendaciones de Google Cloud Retail API debido a una lógica de "optimización" defectuosa en `src/api/core/hybrid_recommender.py`.

### Comportamiento Observado
- **Versión unificada**: 5 recomendaciones de fallback, fuente "hybrid_tfidf_user_redis"
- **Versión fixed**: 1 recomendación real de retail_api, fuente "hybrid_tfidf_user_fixed"

## 🔍 Causa Raíz

En la línea 90-100 de `src/api/core/hybrid_recommender.py`:

```python
# Optimización: si content_weight=1, no llamar al recomendador retail
if self.content_weight < 1.0:  # 🚨 PROBLEMA AQUÍ
    # Intentar obtener recomendaciones de Retail API
    try:
        retail_recs = await self.retail_recommender.get_recommendations(...)
```

**El problema:** Esta "optimización" es **incorrecta para recomendaciones de usuario**. Cuando un usuario solicita recomendaciones personalizadas (sin product_id), el sistema **SIEMPRE** debería intentar obtener recomendaciones de Google Cloud Retail API, independientemente del valor de `content_weight`.

La lógica de `content_weight` debe aplicarse **SOLO** para recomendaciones basadas en productos (cuando hay `product_id`).

## 🔧 Solución Inmediata

### Opción 1: Corrección Mínima (Recomendada)

Modificar la condición en `src/api/core/hybrid_recommender.py` línea ~90:

```python
# ANTES (INCORRECTO):
if self.content_weight < 1.0:
    # Intentar obtener recomendaciones de Retail API...

# DESPUÉS (CORREGIDO):
# Para recomendaciones de usuario (sin product_id), SIEMPRE usar Retail API
# Para recomendaciones de producto (con product_id), aplicar optimización content_weight
if not product_id or self.content_weight < 1.0:
    # Intentar obtener recomendaciones de Retail API...
```

### Opción 2: Corrección Completa

Reestructurar la lógica para mayor claridad:

```python
# Obtener recomendaciones de Retail API
should_use_retail_api = (
    not product_id or  # Siempre para recomendaciones de usuario
    self.content_weight < 1.0  # Solo aplicar optimización para productos
)

if should_use_retail_api:
    try:
        retail_recs = await self.retail_recommender.get_recommendations(
            user_id=user_id,
            product_id=product_id,
            n_recommendations=n_recommendations
        )
        logger.info(f"Obtenidas {len(retail_recs)} recomendaciones de Retail API para usuario {user_id}")
    except Exception as e:
        logger.error(f"Error al obtener recomendaciones de Retail API: {str(e)}")
```

## 📝 Implementación Paso a Paso

1. **Crear respaldo del archivo actual:**
   ```bash
   cp src/api/core/hybrid_recommender.py src/api/core/hybrid_recommender.py.backup
   ```

2. **Aplicar la corrección** usando la Opción 1 (más segura)

3. **Probar la corrección:**
   ```bash
   # Redesplegar la versión unificada
   ./deploy_unified_redis.ps1
   
   # Probar el endpoint problemático
   curl "https://retail-recommender-unified-redis-178362262166.us-central1.run.app/v1/recommendations/user/8816287056181?n=5" \
     -H "X-API-Key: 2fed9999056fab6dac5654238f0cae1c"
   ```

4. **Verificar que ahora devuelve recomendaciones de retail_api**

## 🧪 Validación

Después de aplicar la corrección, el endpoint debería devolver:
- **1 recomendación real** de Google Cloud Retail API
- **Fuente**: "hybrid_tfidf_user_redis" pero con datos de retail_api incluidos
- **Mismo comportamiento** que la versión fixed

## 💡 Mejoras Adicionales

1. **Logging mejorado** para diagnosticar mejor estos problemas:
   ```python
   logger.info(f"content_weight={self.content_weight}, product_id={product_id}, usando_retail_api={should_use_retail_api}")
   ```

2. **Validación de configuración** en el constructor:
   ```python
   if content_weight < 0 or content_weight > 1:
       raise ValueError(f"content_weight debe estar entre 0 y 1, recibido: {content_weight}")
   ```

## 🔍 Prevención Futura

Para evitar este tipo de problemas:

1. **Tests de integración** que validen que las recomendaciones de usuario siempre incluyan retail_api cuando hay datos disponibles
2. **Métricas** que alerten cuando el ratio de recomendaciones de retail_api cae drásticamente
3. **Documentación clara** sobre cuándo se aplican las optimizaciones de content_weight

---

**Nota:** Esta corrección es crítica porque afecta directamente la calidad de las recomendaciones personalizadas, que son la funcionalidad principal del sistema.
