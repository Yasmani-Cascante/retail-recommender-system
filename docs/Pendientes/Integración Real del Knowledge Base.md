# 🤔 Excelente Pregunta: Integración Real del Knowledge Base

---

## 📊 RESPUESTA DIRECTA

**Correcto:** Las políticas están hardcoded como **MVP/Placeholder**.

**En producción real**, tienes **3 opciones** de integración:

---

## 🎯 OPCIÓN 1: CMS/Admin Panel (RECOMENDADO para MVP)

### Cómo Funciona

```
┌─────────────────────────────────────────────────────────┐
│ SHOPIFY ADMIN / CMS                                     │
│                                                         │
│ Pages/Policies:                                        │
│ ├── /policies/returns        (Markdown/HTML)          │
│ ├── /policies/shipping       (Markdown/HTML)          │
│ └── /policies/payment        (Markdown/HTML)          │
└─────────────────────────────────────────────────────────┘
                    ▼
         ┌──────────────────────┐
         │ Shopify API          │
         │ GET /pages/{id}      │
         └──────────────────────┘
                    ▼
         ┌──────────────────────┐
         │ Knowledge Base Cache │
         │ (Redis - 24h TTL)    │
         └──────────────────────┘
                    ▼
         ┌──────────────────────┐
         │ Intent System        │
         │ Returns cached data  │
         └──────────────────────┘
```

### Implementación

```python
# src/api/core/knowledge_base.py (modificado)

import httpx
from src.config.settings import settings
from src.services.cache_service import get_redis_service

class ShopifyKnowledgeBase:
    """
    Knowledge base que obtiene contenido de Shopify.
    """
    
    def __init__(self):
        self.shopify_api_key = settings.SHOPIFY_API_KEY
        self.shopify_store_url = settings.SHOPIFY_STORE_URL
        self.redis = get_redis_service()
        
        # Mapping de sub-intent a Shopify page handle
        self.page_mapping = {
            InformationalSubIntent.POLICY_RETURN: "returns-policy",
            InformationalSubIntent.POLICY_SHIPPING: "shipping-info",
            InformationalSubIntent.POLICY_PAYMENT: "payment-methods",
            # ...
        }
    
    async def get_answer(
        self,
        sub_intent: InformationalSubIntent,
        product_context: Optional[List[str]] = None
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Get answer from Shopify pages.
        """
        
        # 1. Check cache first
        cache_key = f"kb:{sub_intent.value}:{product_context or 'general'}"
        cached = await self.redis.get(cache_key)
        
        if cached:
            logger.debug(f"Cache HIT for {cache_key}")
            return KnowledgeBaseAnswer.parse_raw(cached)
        
        # 2. Fetch from Shopify
        page_handle = self.page_mapping.get(sub_intent)
        if not page_handle:
            return self._get_hardcoded_fallback(sub_intent)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.shopify_store_url}/admin/api/2024-01/pages.json",
                    params={"handle": page_handle},
                    headers={
                        "X-Shopify-Access-Token": self.shopify_api_key
                    },
                    timeout=2.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    page_content = data['pages'][0]['body_html']
                    
                    # Convert HTML to Markdown (simple)
                    markdown_content = self._html_to_markdown(page_content)
                    
                    answer = KnowledgeBaseAnswer(
                        answer=markdown_content,
                        sub_intent=sub_intent,
                        sources=[f"shopify:pages/{page_handle}"]
                    )
                    
                    # 3. Cache for 24 hours
                    await self.redis.setex(
                        cache_key,
                        86400,  # 24 hours
                        answer.json()
                    )
                    
                    return answer
                
        except Exception as e:
            logger.error(f"Shopify API error: {e}")
            # Fallback to hardcoded
            return self._get_hardcoded_fallback(sub_intent)
```

**Pros**:
- ✅ Contenido editable por equipo no-técnico
- ✅ Actualización inmediata (refresh cache)
- ✅ Sincronizado con tienda real

**Contras**:
- ⚠️ Dependencia de Shopify API
- ⚠️ Latencia extra (mitigada con cache)

---

## 🎯 OPCIÓN 2: Base de Datos Propia (Para Escalar)

### Cómo Funciona

```
┌─────────────────────────────────────────────────────────┐
│ ADMIN PANEL (Custom Django/FastAPI)                    │
│                                                         │
│ Tablas:                                                │
│ ├── knowledge_articles (id, sub_intent, content, ...)  │
│ ├── knowledge_categories (ZAPATOS, VESTIDOS, ...)      │
│ └── knowledge_versions (historial de cambios)          │
└─────────────────────────────────────────────────────────┘
                    ▼
         ┌──────────────────────┐
         │ PostgreSQL           │
         │ Full-text search     │
         └──────────────────────┘
                    ▼
         ┌──────────────────────┐
         │ Knowledge Base       │
         │ Query DB + Cache     │
         └──────────────────────┘
```

### Modelo de Datos

```python
# models/knowledge_article.py

from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB

class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    
    id = Column(Integer, primary_key=True)
    sub_intent = Column(String(50), nullable=False, index=True)
    product_category = Column(String(50), nullable=True)  # NULL = general
    title = Column(String(200), nullable=False)
    content_markdown = Column(Text, nullable=False)
    metadata = Column(JSONB, nullable=True)  # {"author": "...", "version": 1}
    
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    
    # Full-text search
    search_vector = Column(TSVector, nullable=True)
```

### Query

```python
async def get_answer(
    self,
    sub_intent: InformationalSubIntent,
    product_context: Optional[List[str]] = None
) -> Optional[KnowledgeBaseAnswer]:
    """
    Query database for knowledge article.
    """
    
    # Try specific category first
    if product_context:
        article = await db.query(KnowledgeArticle).filter(
            KnowledgeArticle.sub_intent == sub_intent.value,
            KnowledgeArticle.product_category == product_context[0]
        ).first()
        
        if article:
            return KnowledgeBaseAnswer(
                answer=article.content_markdown,
                sub_intent=sub_intent,
                sources=[f"db:article:{article.id}"]
            )
    
    # Fallback to general
    article = await db.query(KnowledgeArticle).filter(
        KnowledgeArticle.sub_intent == sub_intent.value,
        KnowledgeArticle.product_category.is_(None)
    ).first()
    
    if article:
        return KnowledgeBaseAnswer(
            answer=article.content_markdown,
            sub_intent=sub_intent,
            sources=[f"db:article:{article.id}"]
        )
    
    return None
```

**Pros**:
- ✅ Control total sobre contenido
- ✅ Búsqueda avanzada (full-text search)
- ✅ Versionado de contenido
- ✅ Sin dependencias externas

**Contras**:
- ⚠️ Requiere construir admin panel
- ⚠️ Mantenimiento de base de datos

---

## 🎯 OPCIÓN 3: Híbrido (RECOMENDADO para Producción)

### Estrategia

```
1. HARDCODED (Fase MVP - Ahora)
   └── Políticas básicas en código
   └── Deploy rápido, validar concepto

2. SHOPIFY CMS (Fase 2 - Mes 1-2)
   └── Migrar contenido a Shopify Pages
   └── Equipo puede editar sin developers
   
3. DATABASE (Fase 3 - Mes 3-6)
   └── Solo si necesitas:
       - Búsqueda semántica avanzada
       - Versionado complejo
       - Múltiples idiomas con traducciones
       - Analytics de qué info se consulta más
```

### Implementación Híbrida

```python
class HybridKnowledgeBase:
    """
    Knowledge base with multiple sources.
    
    Priority:
    1. Database (if available)
    2. Shopify CMS
    3. Hardcoded fallback
    """
    
    def __init__(self):
        self.db_enabled = settings.KNOWLEDGE_DB_ENABLED
        self.shopify_enabled = settings.KNOWLEDGE_SHOPIFY_ENABLED
        
        self.db_kb = DatabaseKnowledgeBase() if self.db_enabled else None
        self.shopify_kb = ShopifyKnowledgeBase() if self.shopify_enabled else None
        self.hardcoded_kb = HardcodedKnowledgeBase()  # Always available
    
    async def get_answer(
        self,
        sub_intent: InformationalSubIntent,
        product_context: Optional[List[str]] = None
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Try sources in priority order.
        """
        
        # Try database first (highest priority)
        if self.db_kb:
            answer = await self.db_kb.get_answer(sub_intent, product_context)
            if answer:
                logger.info("Answer from DATABASE")
                return answer
        
        # Try Shopify CMS
        if self.shopify_kb:
            answer = await self.shopify_kb.get_answer(sub_intent, product_context)
            if answer:
                logger.info("Answer from SHOPIFY")
                return answer
        
        # Fallback to hardcoded
        logger.info("Answer from HARDCODED (fallback)")
        return self.hardcoded_kb.get_answer(sub_intent, product_context)
```

---

## 📋 RECOMENDACIÓN PARA TU CASO

### Para MVP (Ahora - Próximas 2 semanas)

```python
# ✅ USAR: Hardcoded (lo que ya implementamos)

# Razones:
# 1. Deploy inmediato (sin dependencias)
# 2. Valida si Intent Detection realmente mejora UX
# 3. Políticas básicas no cambian frecuentemente
# 4. Fácil migrar después

# Contenido a hardcodear:
# - Política de devoluciones (general + por categoría)
# - Información de envío (tiempos, costos)
# - Métodos de pago
# - Guías de tallas básicas
```

### Para Producción (Mes 1-2)

```python
# ✅ MIGRAR A: Shopify Pages API

# Proceso:
# 1. Crear páginas en Shopify Admin:
#    - /pages/returns-policy
#    - /pages/shipping-info
#    - /pages/payment-methods
#    - /pages/size-guide-dresses
#    - /pages/size-guide-shoes

# 2. Modificar knowledge_base.py:
#    - Fetch de Shopify API
#    - Cache en Redis (24h)
#    - Fallback a hardcoded

# 3. Equipo de contenido puede editar sin código
```

### Para Escalar (Mes 3+)

```python
# ✅ CONSIDERAR: Base de datos propia

# Solo si necesitas:
# - Búsqueda semántica (ML-powered)
# - Versionado complejo
# - Analytics de uso
# - Multi-idioma con traducciones personalizadas
# - A/B testing de respuestas
```

---

## 🎓 LEARNING OPPORTUNITY

**Principio de Desarrollo Ágil**:

> "Start simple, iterate based on real needs"

1. **MVP**: Hardcoded (valida concepto)
2. **V2**: CMS/API (facilita mantenimiento)
3. **V3**: Database (escala avanzada)

**No optimices prematuramente.** Shopify ya tiene tus políticas reales en `/policies/refund-policy`, `/policies/shipping-policy`, etc. 

---

## ✅ ACCIÓN INMEDIATA

**Para el MVP que estamos implementando**:

1. ✅ Mantén hardcoded (como está)
2. ✅ Copia tus políticas reales de Shopify → pega en `knowledge_base.py`
3. ✅ Deploy y valida
4. 📅 En 2-4 semanas: migra a Shopify API (si Intent Detection tiene éxito)

**¿Quieres que te muestre cómo quedaría la integración con Shopify API para Fase 2, o continuamos con Día 2 del plan (Settings + Integración MCP)?**