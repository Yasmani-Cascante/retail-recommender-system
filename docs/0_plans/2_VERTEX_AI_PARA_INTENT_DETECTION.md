# 🚀 VERTEX AI PARA INTENT DETECTION - ANÁLISIS COMPLETO

Excelente pregunta! Vertex AI es una opción **muy sólida** para tu caso, especialmente considerando que ya estás usando **Google Cloud Retail API**. Analicemos a fondo.

---

## 📊 VENTAJAS ESPECÍFICAS DE VERTEX AI

### 1. **Integración nativa con tu stack actual**

```python
# Ya tienes Google Cloud Retail API funcionando:
from google.cloud import retail_v2

# Vertex AI se integra naturalmente:
from google.cloud import aiplatform
from vertexai.language_models import TextClassificationModel

# ✅ Mismo ecosistema, mismas credenciales, mismo billing
```

**Ventajas**:
- ✅ Una sola cuenta de facturación
- ✅ IAM unificado
- ✅ Logging centralizado (Cloud Logging)
- ✅ Monitoring integrado (Cloud Monitoring)

### 2. **AutoML Text Classification (Zero Code ML)**

Vertex AI tiene **AutoML para clasificación de texto** que es PERFECTO para intent detection:

```python
# 1. Preparar datos (CSV simple):
"""
text,label
"¿cuál es la política de devolución?",INFORMATIONAL
"busco vestidos elegantes",TRANSACTIONAL
"cómo funciona el envío?",INFORMATIONAL
...
"""

# 2. Entrenar modelo (UI o SDK):
from google.cloud import aiplatform

aiplatform.init(project='tu-proyecto', location='us-central1')

dataset = aiplatform.TextDataset.create(
    display_name="intent-detection-dataset",
    gcs_source="gs://tu-bucket/training-data.csv"
)

job = aiplatform.AutoMLTextTrainingJob(
    display_name="intent-classifier",
    prediction_type="classification"
)

model = job.run(
    dataset=dataset,
    training_fraction_split=0.8,
    validation_fraction_split=0.1,
    test_fraction_split=0.1,
    model_display_name="intent-detection-model-v1"
)

# 3. Desplegar endpoint:
endpoint = model.deploy(
    machine_type="n1-standard-2",
    min_replica_count=1,
    max_replica_count=3,
    traffic_percentage=100
)
```

**Sin escribir código de ML**, obtienes:
- ✅ Modelo entrenado y validado
- ✅ Métricas automáticas (precision, recall, F1)
- ✅ Endpoint escalable
- ✅ Monitoreo automático

### 3. **Pre-trained Models disponibles**

Vertex AI tiene modelos pre-entrenados que puedes usar directamente:

```python
from vertexai.language_models import TextClassificationModel

# Modelo pre-entrenado de Google (fine-tunable)
model = TextClassificationModel.from_pretrained("text-bison@002")

# Fine-tune con tus datos (solo 100-500 ejemplos necesarios):
tuned_model = model.tune_model(
    training_data="gs://tu-bucket/training-data.jsonl",
    train_steps=1000,
    tuning_job_location="us-central1"
)

# Usar para predicción:
response = tuned_model.predict(
    "¿cuál es la política de devolución?"
)

print(f"Intent: {response.predictions[0]['label']}")
print(f"Confidence: {response.predictions[0]['confidence']}")
```

---

## 💰 ANÁLISIS DE COSTOS

### Costo de entrenamiento (one-time):

```
AutoML Text Classification:
- Entrenamiento: $3.00 USD por hora de nodo
- Tiempo típico: 2-4 horas para dataset de 5000-10000 ejemplos
- Costo total entrenamiento: $6-12 USD

Fine-tuning modelo pre-entrenado:
- $0.008 USD por 1000 tokens procesados
- Dataset de 5000 ejemplos (~50 tokens promedio): $2 USD
```

### Costo de inferencia (ongoing):

```
Online Prediction (endpoint deployed 24/7):
- n1-standard-2: $0.095/hora = $68.40/mes (siempre encendido)
- + $0.000004 por predicción

Batch Prediction (no endpoint, on-demand):
- $0.000004 por predicción
- Ideal para bajo volumen

Ejemplo con 100,000 queries/mes:
- Endpoint: $68.40/mes + $0.40 = $68.80/mes
- Batch: $0.40/mes (pero latencia alta)
```

### Comparación de costos mensuales:

| Solución | Costo/mes | Latencia | Escalabilidad |
|----------|-----------|----------|---------------|
| **Rule-based (actual)** | $0 | 1-5ms | ⭐⭐⭐⭐⭐ |
| **Vertex AI AutoML** | $69-100 | 50-150ms | ⭐⭐⭐⭐ |
| **Vertex AI Batch** | $0.40 | 5-60min | ⭐⭐ |
| **Claude API** | $300-600 | 500-2000ms | ⭐⭐⭐ |

---

## 🏗️ ARQUITECTURA PROPUESTA: HÍBRIDO OPTIMIZADO

### Opción 1: Rule-based + Vertex AI Fallback

```python
from src.api.core.intent_detection import detect_intent as rule_based_detect
from google.cloud import aiplatform

class HybridIntentDetector:
    """
    Detector híbrido: Rule-based primero, Vertex AI para casos difíciles
    
    Flujo:
    1. Rule-based (rápido, gratis)
    2. Si confidence < 0.7 → Vertex AI (preciso, costo)
    3. Cache resultados de Vertex AI (reducir costo)
    """
    
    def __init__(self):
        self.rule_based = get_intent_detector()
        
        # Vertex AI endpoint (lazy load)
        self.vertex_endpoint = None
        self.vertex_enabled = os.getenv("VERTEX_AI_ENABLED", "false") == "true"
        
        # Cache para reducir llamadas a Vertex AI
        self.cache = {}
        self.cache_ttl = 3600  # 1 hora
    
    async def detect(self, query: str) -> IntentDetectionResult:
        """Detección híbrida con fallback inteligente"""
        
        # FASE 1: Rule-based (siempre primero - rápido y gratis)
        rule_result = self.rule_based.detect_intent(query)
        
        # Si alta confidence → usar rule-based
        if rule_result.confidence >= 0.8:
            logger.info(f"✅ High confidence rule-based: {rule_result.confidence:.2f}")
            return rule_result
        
        # Si Vertex AI no está habilitado → usar rule-based aunque sea baja confidence
        if not self.vertex_enabled:
            logger.warning(f"⚠️ Low confidence but Vertex AI disabled: {rule_result.confidence:.2f}")
            return rule_result
        
        # FASE 2: Check cache (evitar llamada a Vertex AI si ya procesamos query similar)
        cache_key = query.lower().strip()
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                logger.info(f"⚡ Cache hit for Vertex AI - saved $0.000004")
                return cached_result
        
        # FASE 3: Vertex AI para casos ambiguos
        logger.info(f"🤖 Low confidence ({rule_result.confidence:.2f}), using Vertex AI")
        
        try:
            vertex_result = await self._predict_with_vertex(query)
            
            # Combinar resultados si ambos tienen confidence similar
            if abs(vertex_result.confidence - rule_result.confidence) < 0.2:
                # Ambos dudan → usar heurística
                final_result = self._resolve_conflict(rule_result, vertex_result)
            else:
                # Vertex AI tiene mayor confidence → confiar en ML
                final_result = vertex_result
            
            # Cache resultado
            self.cache[cache_key] = (final_result, time.time())
            
            return final_result
            
        except Exception as e:
            logger.error(f"❌ Vertex AI error: {e}, falling back to rule-based")
            return rule_result
    
    async def _predict_with_vertex(self, query: str) -> IntentDetectionResult:
        """Llamada a Vertex AI endpoint"""
        
        if not self.vertex_endpoint:
            # Lazy load del endpoint
            aiplatform.init(
                project=os.getenv("GCP_PROJECT_ID"),
                location=os.getenv("GCP_REGION", "us-central1")
            )
            
            self.vertex_endpoint = aiplatform.Endpoint(
                endpoint_name=os.getenv("VERTEX_INTENT_ENDPOINT")
            )
        
        # Predicción
        instances = [{"content": query}]
        response = self.vertex_endpoint.predict(instances=instances)
        
        # Parsear respuesta
        prediction = response.predictions[0]
        
        return IntentDetectionResult(
            primary_intent=prediction['displayNames'][0],  # "INFORMATIONAL" o "TRANSACTIONAL"
            sub_intent=prediction.get('subIntent', 'general'),
            confidence=prediction['confidences'][0],
            reasoning=f"Vertex AI classification (model: {prediction.get('modelVersion', 'unknown')})",
            matched_patterns=[],
            product_context={}
        )
```

### Configuración en .env:

```bash
# Rule-based (siempre activo)
ENABLE_INTENT_DETECTION=true
INTENT_CONFIDENCE_THRESHOLD=0.7

# Vertex AI (opcional - solo para casos difíciles)
VERTEX_AI_ENABLED=true
VERTEX_INTENT_ENDPOINT=projects/123/locations/us-central1/endpoints/456
GCP_PROJECT_ID=tu-proyecto-retail
GCP_REGION=us-central1
```

---

## 📈 ESTIMACIÓN DE COSTO REAL

Asumiendo **100,000 queries/mes**:

### Escenario 1: Solo Rule-based
```
Queries con alta confidence (80%): 80,000 → Rule-based
Queries con baja confidence (20%): 20,000 → Rule-based (fallback)

Costo total: $0/mes
Accuracy estimada: 95%
```

### Escenario 2: Híbrido (Rule-based + Vertex AI)
```
Queries con alta confidence (80%): 80,000 → Rule-based (gratis)
Queries con baja confidence (20%): 20,000 → Vertex AI

Vertex AI calls: 20,000/mes
- Endpoint costo fijo: $68.40/mes
- Predicción variable: 20,000 × $0.000004 = $0.08/mes
- Cache hit rate (50%): ahorra $0.04/mes

Costo total: $68.48/mes
Accuracy estimada: 98%
ROI: +3% accuracy por $68/mes
```

### Escenario 3: Solo Vertex AI
```
Queries totales: 100,000 → Vertex AI

Vertex AI calls: 100,000/mes
- Endpoint costo fijo: $68.40/mes
- Predicción variable: 100,000 × $0.000004 = $0.40/mes

Costo total: $68.80/mes
Accuracy estimada: 98%
ROI: +3% accuracy por $69/mes, pero latencia +50-100ms
```

---

## 🎯 DECISIÓN RECOMENDADA

### **Fase 1: AHORA (próximos 1-3 meses)**

**NO uses Vertex AI todavía** porque:

1. ✅ Rule-based ya tiene 95%+ accuracy (con fix de acentos)
2. ✅ No tienes dataset de 5,000+ queries etiquetadas
3. ✅ Costo $0 vs $69/mes (ahorro $828/año)
4. ✅ Latencia 1-5ms vs 50-150ms (mejor UX)

**Acción**: Implementar logging agresivo:

```python
# En mcp_conversation_handler.py después de intent detection:

if intent_result.confidence < 0.8:
    # Log para análisis futuro
    logger.info(
        "LOW_CONFIDENCE_INTENT",
        extra={
            "query": conversation_query,
            "intent": intent_result.primary_intent,
            "confidence": intent_result.confidence,
            "user_id": validated_user_id,
            "timestamp": time.time()
        }
    )
    
    # Opcional: Enviar a BigQuery para análisis
    await log_to_bigquery(
        table="intent_detection_candidates",
        data={
            "query": conversation_query,
            "rule_based_intent": intent_result.primary_intent,
            "confidence": intent_result.confidence,
            "fallback_used": intent_result.confidence < 0.7
        }
    )
```

---

### **Fase 2: Preparación (meses 3-6)**

**Recolectar datos**:

```sql
-- BigQuery: Analizar queries con baja confidence
SELECT 
    query,
    rule_based_intent,
    confidence,
    COUNT(*) as frequency
FROM `proyecto.dataset.intent_detection_candidates`
WHERE confidence < 0.8
GROUP BY query, rule_based_intent, confidence
ORDER BY frequency DESC
LIMIT 1000
```

**Etiquetar manualmente**:
- Exportar top 5,000 queries únicas
- Etiquetar correctamente (INFORMATIONAL vs TRANSACTIONAL)
- Agregar sub-intents cuando sea claro
- Guardar en Cloud Storage como training data

---

### **Fase 3: Pilot Vertex AI (mes 6-7)**

**Setup mínimo viable**:

```python
# 1. Crear dataset en Vertex AI
from google.cloud import aiplatform

dataset = aiplatform.TextDataset.create(
    display_name="intent-detection-v1",
    gcs_source="gs://tu-bucket/labeled-queries.csv",
    import_schema_uri=aiplatform.schema.dataset.ioformat.text.multi_label_classification
)

# 2. Entrenar modelo AutoML
training_job = aiplatform.AutoMLTextTrainingJob(
    display_name="intent-classifier-v1",
    prediction_type="classification",
    multi_label=False  # Solo 2 clases: INFORMATIONAL, TRANSACTIONAL
)

model = training_job.run(
    dataset=dataset,
    training_fraction_split=0.8,
    validation_fraction_split=0.1,
    test_fraction_split=0.1,
    model_display_name="intent-model-v1",
    
    # Budget de entrenamiento (controlar costo)
    budget_milli_node_hours=2000  # ~2 horas = $6
)

# 3. Evaluar modelo
evaluation = model.get_model_evaluation()
print(f"Precision: {evaluation.metrics['precision']}")
print(f"Recall: {evaluation.metrics['recall']}")
print(f"F1 Score: {evaluation.metrics['f1Score']}")

# 4. Solo desplegar si accuracy > 97%
if evaluation.metrics['f1Score'] > 0.97:
    endpoint = model.deploy(
        machine_type="n1-standard-2",
        min_replica_count=1,
        max_replica_count=2
    )
    print(f"✅ Model deployed: {endpoint.resource_name}")
else:
    print(f"❌ Model accuracy too low, need more training data")
```

---

### **Fase 4: A/B Testing (mes 7-8)**

**Comparar performance**:

```python
# Configuración A/B
AB_TEST_ENABLED = True
AB_TEST_PERCENTAGE = 10  # 10% usa Vertex AI, 90% usa rule-based

async def detect_intent_with_ab_test(query: str) -> IntentDetectionResult:
    """A/B test: Rule-based vs Vertex AI"""
    
    # Decidir grupo (hash del user_id para consistencia)
    user_hash = hash(validated_user_id) % 100
    use_vertex = user_hash < AB_TEST_PERCENTAGE
    
    if use_vertex and VERTEX_AI_ENABLED:
        result = await vertex_detector.detect(query)
        result.metadata["ab_group"] = "vertex_ai"
    else:
        result = rule_based_detector.detect(query)
        result.metadata["ab_group"] = "rule_based"
    
    # Log para análisis
    await log_ab_test_result(
        query=query,
        ab_group=result.metadata["ab_group"],
        intent=result.primary_intent,
        confidence=result.confidence
    )
    
    return result
```

**Métricas a comparar**:
```sql
-- BigQuery: Comparar grupos A/B
SELECT 
    ab_group,
    COUNT(*) as total_queries,
    AVG(confidence) as avg_confidence,
    
    -- Calcular accuracy (requiere feedback del usuario)
    SUM(CASE WHEN user_satisfied = true THEN 1 ELSE 0 END) / COUNT(*) as user_satisfaction,
    
    AVG(response_time_ms) as avg_latency,
    AVG(CASE WHEN knowledge_base_used THEN 1 ELSE 0 END) as kb_usage_rate
FROM `proyecto.dataset.ab_test_results`
GROUP BY ab_group
```

---

## 🚦 DECISION CRITERIA: ¿Cuándo activar Vertex AI?

### ✅ ACTIVAR Vertex AI si:

1. ✅ Rule-based accuracy cae < 90% (basado en feedback usuarios)
2. ✅ Tienes ≥ 5,000 queries etiquetadas de calidad
3. ✅ Presupuesto permite $69-100/mes adicional
4. ✅ Latencia +50ms es aceptable para tu UX
5. ✅ Modelo Vertex AI supera rule-based en al menos +5% accuracy

### ❌ NO activar Vertex AI si:

1. ❌ Rule-based accuracy > 95% (actual estado)
2. ❌ Dataset < 3,000 queries etiquetadas
3. ❌ Presupuesto limitado (mejor invertir en features)
4. ❌ Latencia crítica (<10ms requerido)
5. ❌ Modelo Vertex AI no supera significativamente rule-based

---

## 🎓 ALTERNATIVA: Vertex AI Matching Engine

**Nota importante**: Dado que ya usas **Google Cloud Retail API**, considera que tiene **su propio sistema de intent detection integrado**:

```python
from google.cloud import retail_v2

# Google Retail API puede hacer intent detection automáticamente
search_request = retail_v2.SearchRequest(
    placement="projects/123/locations/global/catalogs/default_catalog/placements/default_search",
    query="política de devolución",
    
    # Activar intent detection nativo
    query_expansion_spec=retail_v2.SearchRequest.QueryExpansionSpec(
        condition=retail_v2.SearchRequest.QueryExpansionSpec.Condition.AUTO
    )
)

response = search_service.search(search_request)

# response.attribution_token contiene info de intent detectado
```

**Ventaja**: Ya lo tienes, sin costo adicional.

---

## 💡 CONCLUSIÓN Y RECOMENDACIÓN FINAL

### Para tu proyecto AHORA:

```
1. ✅ Mantén rule-based actual (95%+ accuracy)
2. ✅ Implementa logging agresivo de queries ambiguas
3. ✅ Recolecta 5,000+ queries etiquetadas (3-6 meses)
4. ⏸️ NO actives Vertex AI todavía (no ROI positivo)
```

### Cuando llegues a Fase 3 (meses 6+):

```
1. ✅ Entrena modelo Vertex AI AutoML ($6-12 setup)
2. ✅ A/B test en 10% de tráfico
3. ✅ Si +5% accuracy → escalar a 100%
4. ✅ Costo estimado: $69/mes bien gastados
```

### Mi stack recomendado final:

```
┌─────────────────────────────────────────────┐
│ TIER 1: Rule-based (80% queries)            │
│ - Latencia: 1-5ms                           │
│ - Costo: $0                                 │
│ - Accuracy: 95%+                            │
└─────────────────────────────────────────────┘
                    ↓ (si confidence < 0.8)
┌─────────────────────────────────────────────┐
│ TIER 2: Vertex AI AutoML (15% queries)      │
│ - Latencia: 50-100ms                        │
│ - Costo: $69/mes                            │
│ - Accuracy: 98%+                            │
└─────────────────────────────────────────────┘
                    ↓ (si confidence < 0.9)
┌─────────────────────────────────────────────┐
│ TIER 3: Google Retail API (5% queries)      │
│ - Latencia: 200-500ms                       │
│ - Costo: incluido en Retail API            │
│ - Accuracy: 99%+                            │
└─────────────────────────────────────────────┘
```

**ROI esperado del híbrido**:
- 95% de queries: resueltas gratis en <5ms (rule-based)
- 4% de queries: resueltas por $0.06/mes en <100ms (Vertex AI)
- 1% de queries: resueltas por Retail API existente

**Costo total**: ~$69/mes para accuracy global de 97-98%

---

¿Quieres que te ayude a implementar alguno de estos componentes? Por ejemplo:
- ✅ Logging pipeline a BigQuery
- ✅ Script de preparación de training data
- ✅ Implementación del hybrid detector
- ✅ Setup de A/B testing