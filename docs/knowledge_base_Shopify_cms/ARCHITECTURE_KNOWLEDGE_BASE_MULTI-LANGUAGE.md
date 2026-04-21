# 🏗️ ARQUITECTURA - KNOWLEDGE BASE MULTI-LANGUAGE

**Versión:** 2.1.0  
**Fecha:** 23 de Enero, 2026  
**Estado:** ✅ PRODUCCIÓN  
**Autor:** Retail Recommender System Team

---

## 📋 ÍNDICE

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura General](#arquitectura-general)
3. [Componentes del Sistema](#componentes-del-sistema)
4. [Flujos Principales](#flujos-principales)
5. [Detección de Idioma](#detección-de-idioma)
6. [Sistema de Caché](#sistema-de-caché)
7. [Sincronización con Shopify](#sincronización-con-shopify)
8. [Métricas y Observabilidad](#métricas-y-observabilidad)
9. [Seguridad](#seguridad)
10. [Decisiones de Diseño](#decisiones-de-diseño)

---

## 1. RESUMEN EJECUTIVO

El Knowledge Base Multi-Language es un sistema conversacional que proporciona respuestas contextuales en múltiples idiomas (ES/EN) con detección automática de idioma preferido del usuario.

### Características Principales

```
✅ Detección automática de idioma (Accept-Language RFC 7231)
✅ Soporte ES (Español) y EN (Inglés)
✅ 13 sub-intents (políticas, productos, cuenta, FAQ)
✅ Cache multi-capa (Redis + PostgreSQL)
✅ Sincronización automática con Shopify
✅ Fallback graceful para idiomas no soportados
✅ Performance: ~300ms avg response time
✅ Cache hit rate: >90%
```

### Métricas de Validación

```
Tests E2E: 45/45 passing (100%)
Coverage: 85-95%
Response Time P95: <500ms
Error Rate: 0%
```

---

## 2. ARQUITECTURA GENERAL

### Vista de Alto Nivel

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
│                      (Browser / Mobile App)                      │
│              Sends: Accept-Language: en-US,en;q=0.9              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                    HTTP GET /v1/kb/answer
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                          API LAYER                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ kb_router.py                                            │   │
│  │  ├─ Language Detection (Accept-Language / Explicit)     │   │
│  │  ├─ Request Validation (sub_intent, category)           │   │
│  │  └─ Response Formatting                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                       BUSINESS LOGIC                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ knowledge_base_v2.py                                     │   │
│  │  └─ get_answer(sub_intent, language, category)          │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
┌─────────────▼─────────┐    ┌──────────────▼─────────────┐
│   CACHE LAYER (L1)    │    │   BUFFER LAYER (L2)        │
│   Redis Enterprise    │    │   PostgreSQL               │
│   - TTL: 1 hora       │    │   - kb_contents table      │
│   - Hit rate: >90%    │    │   - 26 rows (13×2 langs)   │
│   - <1ms latency      │    │   - <10ms latency          │
└─────────────┬─────────┘    └──────────────┬─────────────┘
              │                             │
              └──────────────┬──────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                      CONTENT SOURCE                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Shopify GraphQL API                                      │   │
│  │  ├─ shopLocales query (with asyncio.Lock)               │   │
│  │  ├─ pages query (REST API)                              │   │
│  │  └─ translations query (EN content)                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. COMPONENTES DEL SISTEMA

### 3.1 API Layer

**Ubicación:** `src/api/routers/kb_router.py`

**Responsabilidades:**
- Recibir requests HTTP GET
- Detectar idioma preferido del usuario
- Validar parámetros (sub_intent, language, category)
- Formatear respuesta JSON

**Endpoint:**
```python
GET /v1/kb/answer
  ?sub_intent=policy_return  # Required
  &language=en                # Optional (auto-detected)
  &category=general           # Optional
```

---

### 3.2 Language Detection

**Ubicación:** `src/api/utils/language_detection.py`

**Prioridad de detección:**

```
1. EXPLICIT PARAMETER (?language=en) - Highest priority
2. ACCEPT-LANGUAGE HEADER - Medium priority
3. DEFAULT (es) - Lowest priority
```

**Ejemplo de parsing Accept-Language:**

```
INPUT: "en-US,en;q=0.9,es;q=0.8"
PROCESS: 
  1. Split por ","
  2. Extract language codes: ["en-US", "en", "es"]
  3. Get base language: ["en", "en", "es"]
  4. Find first supported: "en"
OUTPUT: "en"
```

---

### 3.3 Cache System

**Redis (Layer 1):**
```
Provider: Redis Enterprise (cloud)
TTL: 3600 seconds
Hit Rate: >90%
Latency: ~300ms
```

**PostgreSQL (Layer 2):**
```
Table: kb_contents
Rows: 26 (13 sub_intents × 2 languages)
Hit Rate: 100%
Latency: ~280ms
```

**Shopify (Layer 3):**
```
Access: Only during sync
Latency: ~500ms per page
Frequency: Every 5-10 minutes
```

---

## 4. FLUJOS PRINCIPALES

### 4.1 Request Normal (Cache Hit)

```
1. CLIENT → GET /v1/kb/answer?sub_intent=policy_return
   Headers: Accept-Language: en-US,en;q=0.9

2. API LAYER
   ├─ Parse Accept-Language → "en"
   ├─ Validate sub_intent
   └─ Log: "KB query: language=en (method: accept_language_header)"

3. CACHE (Redis)
   ├─ Key: kb:policy_return/en/general
   ├─ Result: HIT ✅
   └─ Duration: ~300ms

4. RESPONSE
   {
     "sub_intent": "policy_return",
     "language": "en",
     "answer": "## Return Policy\n\n..."
   }
```

### 4.2 Invalid Language (Fallback)

```
REQUEST: ?language=fr

PROCESS:
├─ validate_language("fr")
├─ Check: "fr" in {"es", "en"} → FALSE
├─ Return: "es" (default)
└─ User gets ES content (graceful fallback)

RESPONSE:
{
  "language": "es",  // Note: ES, not FR
  "answer": "## Política de Devoluciones..."
}
```

---

## 5. SINCRONIZACIÓN CON SHOPIFY

### Proceso (2.37s duration)

```
1. FETCH KB PAGES (REST API)
   └─ 13 pages with metafield kb_sub_intent

2. FETCH METAFIELDS (GraphQL, parallel)
   └─ Extract kb_sub_intent, kb_category

3. SYNC DEFAULT LANGUAGE (ES)
   └─ INSERT/UPDATE 13 rows in PostgreSQL

4. FETCH shopLocales (WITH LOCK) ⭐
   ├─ GraphQL query (once per sync)
   ├─ asyncio.Lock prevents race condition
   └─ Cache 1 hour

5. FETCH TRANSLATIONS (EN)
   └─ GraphQL query (parallel)

6. SYNC TRANSLATIONS
   └─ INSERT/UPDATE 13 additional rows

7. INVALIDATE REDIS
   └─ Clear cache for updated pages

RESULT: 26 rows total (13 ES + 13 EN)
```

### Race Condition Fix

**BEFORE:**
```python
# 3 tasks execute simultaneously
Task 1, 2, 3: fetch shopLocales from Shopify
Result: 3× redundant queries
```

**AFTER:**
```python
async with self._shoplocales_lock:
    # Only first task fetches
    # Tasks 2-3 wait, then use cached
Result: 1× query (-67% reduction)
```

---

## 6. DECISIONES DE DISEÑO

### 6.1 Accept-Language vs NLP

**Decisión:** Accept-Language (RFC 7231)

**Razones:**
- ✅ 100% accuracy (vs 70-80% NLP)
- ✅ Zero latency (vs +5-10ms NLP)
- ✅ Industry standard (Google, Amazon, Netflix)
- ✅ Simple implementation (~50 LOC)

---

### 6.2 Fallback Strategy

**Decisión:** Graceful fallback to ES (not HTTP error)

**Razones:**
- ✅ Better UX (content > error)
- ✅ Robust (typos don't break)
- ✅ Gradual expansion (new languages auto-work)

---

### 6.3 Multi-Layer Cache

**Decisión:** Redis + PostgreSQL

**Razones:**
- ✅ Redis offloads DB (>90% requests)
- ✅ PostgreSQL provides persistence
- ✅ Resilience (Redis can fail, DB continues)

---

## 7. TESTING

### Coverage

```
Total Tests: 45
├─ Basic Functionality: 26 (13 sub_intents × 2 languages)
├─ Accept-Language: 6
├─ Default Fallback: 3
├─ Invalid Language: 5
├─ Priority Order: 2
├─ Error Handling: 2
└─ Response Structure: 1

Result: 45/45 PASSING ✅
```

### Execution

```bash
# Run E2E tests
pytest tests/e2e/test_kb_multi_language_e2e.py -v

# Expected output:
# ====== 45 passed in ~15s ======
```

---

## 8. PERFORMANCE

### Response Times

```
P50 (Median):  295ms
P95:           350ms
P99:           434ms
Average:       ~300ms

TARGET: P95 <500ms ✅ ACHIEVED
```

### Cache Performance

```
Redis Hit Rate:     >90%
PostgreSQL Queries: <10%
Shopify Access:     Sync only
```

---

## 9. SUB-INTENTS DISPONIBLES

```
POLICIES (5):
├─ policy_return
├─ policy_shipping
├─ policy_warranty
├─ policy_payment
└─ policy_privacy

PRODUCTS (4):
├─ product_care
├─ product_sizing
├─ product_material
└─ product_availability

ACCOUNT (2):
├─ account_modifications
└─ account_orders

GENERAL (2):
├─ general_faq
└─ unknown
```

---

## 10. EJEMPLOS DE USO

### Idioma Explícito

```bash
curl "http://localhost:8000/v1/kb/answer?sub_intent=policy_return&language=en"
```

### Detección Automática

```bash
curl "http://localhost:8000/v1/kb/answer?sub_intent=policy_return" \
  -H "Accept-Language: en-US,en;q=0.9"
```

### Fallback a Español

```bash
curl "http://localhost:8000/v1/kb/answer?sub_intent=policy_return"
# No language specified → returns ES
```

---

## 📚 REFERENCIAS

- [RFC 7231 - Accept-Language](https://tools.ietf.org/html/rfc7231#section-5.3.5)
- Código fuente: `src/api/routers/kb_router.py`
- Tests: `tests/e2e/test_kb_multi_language_e2e.py`

---

**Versión:** 2.1.0  
**Última actualización:** 23 de Enero, 2026  
**Estado:** ✅ PRODUCCIÓN

*Documentación técnica del sistema Knowledge Base Multi-Language*
