# Análisis Técnico — Liquid AI vs Transformers — Decisión de Arquitectura — 11 Abr 2026

## Executive Summary

Liquid AI es técnicamente interesante, pero adoptar sus modelos como capa de inferencia conversacional en el sistema sería una apuesta prematura y mal calibrada para el problema real. El cuello de botella no está en la arquitectura neuronal del modelo conversacional — está en el cold start de Cloud Run, el peso de PyTorch/sentence-transformers en el startup crítico, y la latencia del pipeline completo de personalización (MCPPersonalizationEngine + Shopify API calls + Redis). Liquid AI no resuelve ninguno de estos problemas.

**Decisión: No integrar Liquid AI ahora. Integrar transformers pequeños con lazy loading primero.**

---

## 1. Comparativa Técnica

### Transformers clásicos (Sentence-Transformers, MiniLM)

- Arquitectura de atención multi-cabeza con comprensión semántica real
- Entienden negaciones, referencias anafóricas y matices de idioma
- Debilidad: PyTorch ~600MB instalado, ~900ms de carga en frío
- Inferencia por query en CPU: 10–50ms (aceptable una vez caliente)
- Casos de uso en este sistema: intent detection semántico (lazy loaded), embeddings de catálogo pre-computados en Redis, re-ranking

### Liquid Foundation Models (LFM2)

- Arquitectura híbrida: convoluciones + Gated Multi-Query Attention + MoE (64 expertos, top-4 routing)
- Ventaja: eficiencia paramétrica (~50% menos parámetros), inferencia sub-20ms
- **Limitación crítica: ventana de contexto de solo 33K tokens**
- Ecosistema muy pequeño (~2.000 desarrolladores)
- Diseñados como API externa o con plataforma LEAP, no como módulos en proceso FastAPI
- **No son un reemplazo de Claude para generación conversacional**

### Distinción conceptual clave

Liquid AI en producción con Shopify reemplaza el motor de búsqueda y ranking de productos (equivalente al TF-IDF + HybridRecommender), **no** la capa conversacional de MCPPersonalizationEngine.

---

## 2. Evaluación para Google Cloud Run

### ¿Liquid AI reduce el cold start? No directamente.

El cold start viene de:

- Arranque de instancia Docker (~3–5s)
- Imports de FastAPI + dependencias (~2–3s)
- Carga del modelo TF-IDF pkl (~1–2s)
- Warm-up del cliente Anthropic (~0.5s)
- Conexión Redis (~0.5s)

Liquid como API remota no cambia ninguno de estos factores. Liquid local (LEAP) requiere GPUs dedicadas — inviable en Cloud Run estándar para este volumen.

### Impacto en recursos

| Componente | RAM actual | Con Liquid API | Con Liquid local |
| --- | --- | --- | --- |
| FastAPI + TF-IDF + Redis | ~330MB | ~330MB | ~330MB + 4–16GB GPU |

Liquid local es inviable en Cloud Run sin GPUs.

---

## 3. Propuesta de Arquitectura

Si se explora Liquid AI, la única arquitectura coherente es:

```
Widget → FastAPI handler
    ├─ Intent detection (rule-based + sklearn + [MiniLM lazy])
    ├─ HybridRecommender
    │       ├─ TF-IDF (actual)          [corto plazo: mantener]
    │       └─ Liquid API (ranking)     [medio plazo: A/B test]
    ├─ MCPPersonalizationEngine
    │       └─ Claude Haiku             [mantener siempre]
    └─ MarketAdapter
```

Liquid entraría **solo como capa de ranking semántico**, controlada por feature flag. No toca la capa conversacional ni el cold start path.

---

## 4. Pros & Cons

### Liquid AI — Pros

- Inferencia sub-20ms para ranking de productos
- Precios muy bajos ($0.01–0.03 por 1M tokens de input)
- Respaldo estratégico de Shopify a largo plazo
- Compatible con OpenAI SDK

### Liquid AI — Contras

- Ecosistema extremadamente pequeño (~2.000 desarrolladores)
- Ventana de contexto de 33K tokens — limitante para sesiones ricas
- No es modelo conversacional — no reemplaza Claude
- LEAP no probado en producción a escala
- No resuelve el cold start de Cloud Run
- Acceso real requiere negociación enterprise
- Escasa documentación de edge cases

---

## 5. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
| --- | --- | --- | --- |
| Liquid API down / SLA inadecuado | Media | Alto | Mantener TF-IDF como fallback síncrono |
| Contexto 33K insuficiente | Alta | Medio | Truncamiento inteligente del historial |
| Ecosistema sin soporte para edge cases | Alta | Medio | PoC en 5% de tráfico antes de comprometer |
| Costos reales vs precios publicados | Alta | Medio | Negociar pricing antes de escalar |
| Dependencia externa adicional en path crítico | Media | Alto | Solo en paths no críticos con timeout + fallback |

---

## 6. Recomendación Final y Plan de Acción

### Decisión: No integrar Liquid AI ahora

**Justificación:**

1. El bottleneck está en el pipeline de personalización (MCPPersonalizationEngine + Shopify API + Claude), no en la calidad del ranking. Liquid no toca ese bottleneck.
2. El plan correcto ya está documentado (análisis 09/04): lazy loading de MiniLM, embeddings pre-computados en Redis. Resuelve el 80% de lo que Liquid resolvería, con cero riesgo de adopción.
3. Liquid tiene valor estratégico a 6+ meses (Phase 3 microservicios), no inmediato.

### Plan de acción

**Corto plazo (1–2 meses):**

- Implementar `paraphrase-multilingual-MiniLM-L12-v2` con lazy loading para intent detector semántico
- Pre-computar embeddings del catálogo en Redis para búsqueda semántica
- Mantener rule-based + sklearn como capa primaria (sin regresión)

**Medio plazo (3–6 meses):**

- Cuando microservicios estén en marcha, probar Liquid en un `ranking-service` aislado con 5–10% del tráfico
- Medir latencia real, calidad de recomendaciones y fiabilidad de la API

**Largo plazo (6+ meses):**

- Si Liquid cumple en el A/B test y Shopify profundiza la integración, evaluar reemplazar TF-IDF en el microservicio de ranking
- Claude Haiku se mantiene como capa conversacional en cualquier escenario