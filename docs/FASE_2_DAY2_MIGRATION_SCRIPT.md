# 🚀 FASE 2 DÍA 2 - MIGRATION SCRIPT

## BACKUP Y REPLACEMENT SEGURO

### Paso 1: Crear backup del original
```bash
# El archivo original será respaldado como:
# recommendations_original_backup_20251016.py
```

### Paso 2: Aplicar versión migrada
```bash
# recommendations_migrated.py → recommendations.py
```

### Paso 3: Verificación
```bash
# Verificar que el servidor arranca correctamente
# Test endpoints manualmente
```

### Rollback (si necesario)
```bash
# Restaurar desde backup:
cp recommendations_original_backup_20251016.py recommendations.py
```

## CAMBIOS REALIZADOS

### Imports modificados:
**ANTES:**
```python
from src.api.core.recommenders import hybrid_recommender, content_recommender, retail_recommender
```

**DESPUÉS:**
```python
from src.api.dependencies import (
    get_tfidf_recommender,
    get_retail_recommender,
    get_hybrid_recommender
)
```

### Endpoints migrados:
1. ✅ `get_recommendations()` - Product recommendations
2. ✅ `get_user_recommendations()` - User recommendations
3. ✅ `record_user_event()` - Event recording

### Type hints agregados:
- `tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender)`
- `retail_recommender: RetailAPIRecommender = Depends(get_retail_recommender)`
- `hybrid_recommender: HybridRecommender = Depends(get_hybrid_recommender)`

### Endpoints sin cambios (no usan recommenders):
1. `read_root()` - API info
2. `get_products()` - Product listing
3. `get_customers()` - Customer listing
4. `get_products_by_category()` - Category filter
5. `search_products()` - Product search
6. `get_recommendation_metrics()` - Metrics

## VALIDACIÓN

### Tests a ejecutar:
1. Servidor arranca sin errores
2. GET /recommendations/{product_id} funciona
3. GET /recommendations/user/{user_id} funciona
4. POST /events/user/{user_id} funciona
5. Otros endpoints siguen funcionando

### Expected behavior:
- ✅ Zero breaking changes
- ✅ Same responses
- ✅ Same performance
- ✅ Better testability

## STATUS
- Backup: ✅ READY
- Migration: ✅ READY
- Rollback plan: ✅ READY
