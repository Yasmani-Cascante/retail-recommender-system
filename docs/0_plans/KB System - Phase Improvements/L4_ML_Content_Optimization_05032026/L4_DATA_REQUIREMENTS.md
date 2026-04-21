# L4 — ML Content Optimization: Data Requirements & Función Objetivo
## Retail Recommender System v2.1.0

**Fecha de creación:** 05 de Marzo, 2026
**Autor:** Arquitecto Cloud Senior
**Estado:** Definición completada. Implementación: pendiente dataset ≥ 3 semanas.

---

## 1. Función Objetivo de L4

L4 (ML Content Optimization) tiene un objetivo preciso:

> **"Determinar qué versión del contenido KB produce mayor tasa de resolución de intent en la primera consulta del usuario."**

Esto se traduce en maximizar la métrica:

```
Intent Resolution Rate (IRR) =
    conversaciones_con_respuesta_satisfactoria_en_1_turno
    ──────────────────────────────────────────────────────
    total_conversaciones_que_consultaron_KB
```

### Métricas de Negocio Candidatas

| ID | Métrica | Definición | Fuente de Datos | Prioridad |
|----|---------|------------|-----------------|-----------|
| **M1** | Intent Resolution Rate | Conversación termina sin fallback al primer turno | MCP conversation logs (structlog) | ⭐ PRIMARIA |
| **M2** | KB Lookup Latency | Latencia cuando KB es el path crítico (p95) | Prometheus: `kb_lookup_duration_seconds` | Secundaria |
| **M3** | Re-consulta Rate | Usuario hace la misma pregunta >1 vez en sesión | Conversation state (Redis) | Secundaria |
| **M4** | Fallback Rate | Porcentaje de respuestas que usan fallback vs KB | MCP router logs | Complementaria |

**Decisión recomendada: M1 como función objetivo principal, M2+M3 como regularizadores.**

---

## 2. Criterios Mínimos de Dataset para Iniciar L4

### 2.1 Criterios Cuantitativos (Neon — kb_content_versions)

```sql
-- QUERY 1: Estado actual del historial de versiones
-- Ejecutar antes de iniciar L4. Criterio de done: ≥ 3 versiones/contenido promedio
SELECT
    sub_intent,
    language,
    COUNT(*) AS version_count,
    MIN(created_at) AS first_version,
    MAX(created_at) AS latest_version,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 86400 AS days_of_history
FROM kb_content_versions
GROUP BY sub_intent, language
ORDER BY version_count DESC;

-- CRITERIO: version_count promedio ≥ 3 para ≥ 80% de los sub_intents
-- Si no se cumple: esperar más tiempo de acumulación
```

```sql
-- QUERY 2: Velocidad de acumulación de versiones (proyección)
SELECT
    DATE_TRUNC('week', created_at) AS week,
    COUNT(*) AS new_versions,
    COUNT(DISTINCT sub_intent) AS sub_intents_updated
FROM kb_content_versions
GROUP BY week
ORDER BY week DESC
LIMIT 8;

-- INTERPRETACIÓN:
-- Si new_versions/week >= 5: dataset suficiente en ~3-4 semanas
-- Si new_versions/week < 2: considerar estrategia de datos sintéticos
```

```sql
-- QUERY 3: Coverage check — ¿todos los sub_intents tienen versiones?
SELECT
    kc.sub_intent,
    kc.language,
    COUNT(kcv.id) AS version_count,
    kc.updated_at AS last_content_update
FROM kb_contents kc
LEFT JOIN kb_content_versions kcv
    ON kc.sub_intent = kcv.sub_intent
    AND kc.language = kcv.language
GROUP BY kc.sub_intent, kc.language, kc.updated_at
HAVING COUNT(kcv.id) = 0
ORDER BY kc.sub_intent;

-- Si retorna filas: sub_intents sin historial — monitorear manualmente
-- Si retorna vacío: ✅ cobertura completa
```

### 2.2 Criterios de Observabilidad (prerequisitos técnicos)

Antes de iniciar L4, estos deben estar activos:

```
✅ configure_structlog() activo          → COMPLETADO (05/03/2026)
⬜ GCP Cloud Monitoring PASO 7           → Verificar env vars en Cloud Run
⬜ Prometheus scraping activo            → Al menos 1 métrica con datos últimas 24h
⬜ kb_content_versions con ≥ 3 semanas  → Verificar con Query 1 arriba
⬜ IRR baseline establecido              → Medir 2 semanas antes de L4 activo
```

---

## 3. Arquitectura Propuesta de L4

### 3.1 Pipeline de Training Data

```
Shopify CMS (marketing actualiza página)
    ↓ webhook translations/update (M4)
    ↓
PostgreSQL kb_content_versions (L2)
    ↓ nueva versión guardada con timestamp
    ↓
Neon DB historial: {sub_intent, language, content_markdown, version_number, created_at}
    ↓ (3-4 semanas de acumulación)
    ↓
L4 Training Pipeline:
    feature_extraction(content_markdown) → TF-IDF features + embedding features
    correlation_with_metrics(version, IRR_window) → label per version
    model = train(features, labels)
    content_score = model.predict(new_content)
```

### 3.2 Opciones de Modelo ML

| Opción | Complejidad | Datos necesarios | Tiempo de desarrollo |
|--------|-------------|------------------|----------------------|
| **TF-IDF refinado** (baseline) | Baja | 3 semanas | 1-2 semanas | 
| **Embedding semántico** (sentence-transformers) | Media | 4-6 semanas | 2-3 semanas |
| **LLM-as-judge** (Claude API) | Alta | 2 semanas (datos sintéticos) | 3-4 semanas |

**Recomendación inicial:** TF-IDF refinado como baseline medible, escalable a embeddings con más datos.

---

## 4. Variables de Entorno Adicionales para L4

Agregar a `.env` y Cloud Run cuando se inicie L4:

```bash
# L4 Feature flags
L4_CONTENT_SCORING_ENABLED=false       # Activar cuando modelo esté listo
L4_MIN_VERSIONS_FOR_SCORING=3          # Mínimo de versiones para score confiable
L4_SCORING_MODEL=tfidf                 # tfidf | embeddings | llm_judge
L4_IRR_WINDOW_DAYS=7                   # Ventana para calcular IRR por versión
```

---

## 5. Criterios de Done para Iniciar L4

```
[ ] Query 1 → version_count promedio ≥ 3 para ≥ 80% de sub_intents
[ ] Query 2 → ≥ 3 semanas de historial continuo
[ ] GCP Cloud Monitoring → datos reales en últimas 24h
[ ] IRR baseline → medido durante 2 semanas pre-L4
[ ] Decisión de modelo → tfidf / embeddings / llm_judge documentada
[ ] Rama Git creada → feature/l4-content-optimization
```

**Fecha estimada earliest para iniciar L4:** ~26 de Marzo, 2026 (3 semanas desde 05/03/2026)

---

## 6. Log de Decisiones

| Fecha | Decisión | Razón |
|-------|----------|-------|
| 05/03/2026 | Consolidar observabilidad ANTES de L4 | L4 necesita logging estructurado activo para extraer features + dataset sin historial (0 días en Neon) |
| 05/03/2026 | M1 (IRR) como función objetivo principal | Métrica más directa de utilidad del contenido KB |
| 05/03/2026 | TF-IDF refinado como modelo baseline | Menor complejidad, datos disponibles sooner, medible vs baseline actual |
