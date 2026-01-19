# 📚 GUÍA MAESTRA: Agregar Páginas KB al Sistema

## 🎯 OBJETIVO

Escalar el Knowledge Base de 1 página a 15-20 páginas cubriendo los temas más frecuentes en e-commerce retail.

---

## 📊 TAXONOMÍA COMPLETA DE SUB_INTENTS

### 1. POLÍTICAS (Policy) - 5 sub_intents

| Sub-Intent | Descripción | Prioridad | Ejemplo Query |
|------------|-------------|-----------|---------------|
| `policy_return` | Devoluciones y cambios | 🔥 P1 | "¿Cómo devolver un producto?" |
| `policy_shipping` | Envíos y tiempos de entrega | 🔥 P1 | "¿Cuánto tarda el envío?" |
| `policy_warranty` | Garantías y defectos | ⚠️ P2 | "¿Tiene garantía?" |
| `policy_payment` | Métodos de pago | ⚠️ P2 | "¿Aceptan PayPal?" |
| `policy_privacy` | Privacidad y datos | 📋 P3 | "¿Qué hacen con mis datos?" |

### 2. PRODUCTOS (Product) - 5 sub_intents

| Sub-Intent | Descripción | Prioridad | Ejemplo Query |
|------------|-------------|-----------|---------------|
| `product_sizing` | Tallas y medidas | 🔥 P1 | "¿Qué talla debo pedir?" |
| `product_care` | Cuidado y mantenimiento | ⚠️ P2 | "¿Cómo lavo mi vestido?" |
| `product_material` | Materiales y composición | ⚠️ P2 | "¿De qué está hecho?" |
| `product_availability` | Stock y disponibilidad | 📋 P3 | "¿Cuándo vuelve en stock?" |
| `product_recommendations` | Sugerencias y combos | 📋 P3 | "¿Qué me recomiendan?" |

### 3. CUENTA Y ÓRDENES (Account) - 3 sub_intents

| Sub-Intent | Descripción | Prioridad | Ejemplo Query |
|------------|-------------|-----------|---------------|
| `account_orders` | Rastreo y estado de órdenes | 🔥 P1 | "¿Dónde está mi pedido?" |
| `account_modifications` | Modificar o cancelar orden | ⚠️ P2 | "¿Puedo cambiar mi dirección?" |
| `account_profile` | Actualizar perfil | 📋 P3 | "¿Cómo cambio mi email?" |

### 4. GENERAL (General) - 2 sub_intents

| Sub-Intent | Descripción | Prioridad | Ejemplo Query |
|------------|-------------|-----------|---------------|
| `general_faq` | Preguntas frecuentes generales | ⚠️ P2 | "¿Tienen tienda física?" |
| `general_contact` | Contacto y soporte | 📋 P3 | "¿Cómo los contacto?" |

---

## 🗂️ ESTRUCTURA DE CATEGORÍAS (Category)

### Approach: General + Específico

**Regla:** Solo agregar `category` cuando el contenido es específico a un tipo de producto.

### Categorías Disponibles

```json
[
  null,           // General (aplica a todo)
  "ZAPATOS",      // Calzado
  "VESTIDOS",     // Vestidos
  "ACCESORIOS",   // Accesorios
  "ROPA",         // Ropa general
  "JOYERIA"       // Joyería
]
```

### Ejemplos de Uso

**Páginas GENERALES (category = null):**
- `policy_return` - Aplica a todos los productos
- `policy_shipping` - Aplica a todos los productos
- `policy_payment` - Aplica a todos los productos

**Páginas ESPECÍFICAS (category = "ZAPATOS"):**
- `product_care` + category="ZAPATOS" - "Cómo limpiar zapatos"
- `product_sizing` + category="ZAPATOS" - "Guía de tallas de zapatos"

**Páginas ESPECÍFICAS (category = "VESTIDOS"):**
- `product_care` + category="VESTIDOS" - "Cómo lavar vestidos"
- `product_material` + category="VESTIDOS" - "Telas de vestidos"

---

## 🌍 ESTRATEGIA MULTI-LANGUAGE

### Approach Actual: Páginas Separadas

Cada idioma = 1 página con su propio metafield `language`.

**Idiomas Soportados:**
- `es` - Español (default, obligatorio)
- `en` - Inglés (opcional)
- `pt` - Portugués (futuro)

### Naming Convention

**Handle (URL slug):**
```
{sub_intent}-{language}[-{category}]

Ejemplos:
- policy-return-es           → Devoluciones (ES, general)
- policy-return-en           → Returns (EN, general)
- product-care-es-zapatos    → Cuidado zapatos (ES)
- product-sizing-en-vestidos → Sizing dresses (EN)
```

**Título:**
```
[ES/EN/PT] Título descriptivo

Ejemplos:
- [ES] ¿Cómo devolver un producto?
- [EN] How to return a product?
- [ES] Cuidado de zapatos
- [EN] Shoe care guide
```

---

## 📋 ROADMAP DE IMPLEMENTACIÓN

### Sprint 1: Páginas Core (Semana 1)

**Priority 1 (P1) - 5 páginas:**

1. ✅ `policy_return` (es) - Ya creada
2. 🆕 `policy_shipping` (es)
3. 🆕 `product_sizing` (es)
4. 🆕 `account_orders` (es)
5. 🆕 `policy_payment` (es)

**Meta:** Cubrir 80% de queries más frecuentes.

### Sprint 2: Páginas Secundarias (Semana 2)

**Priority 2 (P2) - 5 páginas:**

6. `policy_warranty` (es)
7. `product_care` (es) - General
8. `product_material` (es) - General
9. `account_modifications` (es)
10. `general_faq` (es)

**Meta:** Cobertura completa de temas principales.

### Sprint 3: Páginas Específicas (Semana 3)

**Priority 2 (P2) - 5 páginas específicas:**

11. `product_care` (es) + category="ZAPATOS"
12. `product_care` (es) + category="VESTIDOS"
13. `product_sizing` (es) + category="ZAPATOS"
14. `product_sizing` (es) + category="VESTIDOS"
15. `product_material` (es) + category="JOYERIA"

**Meta:** Información detallada por categoría.

### Sprint 4: Multi-Language (Semana 4)

**Inglés - 5 páginas más importantes:**

16. `policy_return` (en)
17. `policy_shipping` (en)
18. `product_sizing` (en)
19. `account_orders` (en)
20. `policy_payment` (en)

**Meta:** Soporte básico en inglés.

---

## 🎯 PROYECCIÓN FINAL

| Fase | Páginas | Cobertura | Timeline |
|------|---------|-----------|----------|
| Actual | 1 | 15% | ✅ Completo |
| Sprint 1 | 5 | 80% | Semana 1 |
| Sprint 2 | 10 | 95% | Semana 2 |
| Sprint 3 | 15 | 98% | Semana 3 |
| Sprint 4 | 20 | 100% | Semana 4 |

---

## 📊 MÉTRICAS DE ÉXITO

### KPIs por Sprint

| Métrica | Sprint 1 | Sprint 2 | Sprint 3 | Sprint 4 |
|---------|----------|----------|----------|----------|
| Páginas en DB | 5 | 10 | 15 | 20 |
| Sync time | <2s | <3s | <4s | <5s |
| Query coverage | 80% | 95% | 98% | 100% |
| Idiomas | 1 (es) | 1 (es) | 1 (es) | 2 (es+en) |

### Validación por Página

Cada página nueva debe pasar:

```
✅ Página creada en Shopify
✅ Metafield configurado correctamente
✅ Visible en Shopify Admin
✅ Detectada por sistema (sync logs)
✅ Guardada en PostgreSQL
✅ API endpoint responde
✅ Cache funcionando
✅ Sin errores en logs
```

---

## 🔧 HERRAMIENTAS DE SOPORTE

### 1. Template JSON Generator

Ver: `KB_PAGE_TEMPLATES.md`

### 2. Validation Checklist

Ver: `KB_PAGE_VALIDATION_CHECKLIST.md`

### 3. Content Templates

Ver: `KB_CONTENT_TEMPLATES.md`

### 4. Bulk Creation Script

Ver: `create_kb_pages_bulk.py`

### 5. Health Check Endpoint

Ver: `KB_HEALTH_CHECK_ENDPOINT.md`

---

## 📚 PRÓXIMOS ARCHIVOS A CREAR

1. **KB_PAGE_TEMPLATES.md** - Templates JSON para cada sub_intent
2. **KB_CONTENT_TEMPLATES.md** - Templates de contenido en español
3. **KB_MARKETING_GUIDE.md** - Guía para marketing team (non-technical)
4. **KB_PAGE_VALIDATION_CHECKLIST.md** - Checklist de validación
5. **create_kb_pages_bulk.py** - Script para creación masiva
6. **KB_HEALTH_CHECK_ENDPOINT.md** - Endpoint de monitoreo

---

## 🎓 BEST PRACTICES

### 1. Naming Consistency

✅ **DO:**
- `policy_return` (lowercase, underscore)
- `product_care`
- `account_orders`

❌ **DON'T:**
- `Policy_Return` (uppercase)
- `product-care` (hyphen)
- `accountOrders` (camelCase)

### 2. Content Quality

✅ **DO:**
- Claro y conciso (200-500 palabras)
- Formato con headers (H2, H3)
- Listas cuando sea apropiado
- Links a páginas relacionadas

❌ **DON'T:**
- Contenido duplicado
- Demasiado técnico
- Sin estructura
- Información desactualizada

### 3. Metafield Structure

✅ **DO:**
```json
{
  "sub_intent": "policy_return",
  "language": "es",
  "category": null,
  "tags": ["policy", "returns", "refunds"]
}
```

❌ **DON'T:**
```json
{
  "subIntent": "policy_return",  // camelCase
  "lang": "es",                  // abbreviated
  "category": "",                // empty string instead of null
  "tags": "policy,returns"       // string instead of array
}
```

### 4. Testing Before Deploy

✅ **DO:**
1. Test en staging primero
2. Validar JSON syntax
3. Verificar sync logs
4. Test API endpoint
5. Check cache

❌ **DON'T:**
- Crear directamente en producción
- Skip validation
- No revisar logs

---

## 🚨 TROUBLESHOOTING COMÚN

### Problema 1: Página no detectada

**Síntomas:**
```
INFO - Filtered KB pages: 0 KB pages, 3 skipped
```

**Causas posibles:**
1. Metafield no existe
2. Metafield mal formateado (JSON inválido)
3. `sub_intent` falta
4. `body_html` vacío

**Solución:**
1. Verificar metafield en Shopify Admin
2. Validar JSON en https://jsonlint.com
3. Verificar que `sub_intent` existe
4. Agregar contenido a la página

### Problema 2: Error de sync

**Síntomas:**
```
ERROR - Failed to sync page 123456
```

**Causas posibles:**
1. PostgreSQL connection error
2. Invalid data types
3. Redis error

**Solución:**
1. Check DB connection
2. Verificar tipos de datos
3. Check Redis logs

### Problema 3: API no responde

**Síntomas:**
```
GET /api/v1/kb/answer → 404 Not Found
```

**Causas posibles:**
1. Página no sincronizada
2. Cache vacío
3. Sub-intent incorrecto

**Solución:**
1. Trigger manual sync
2. Verificar DB
3. Verificar sub_intent exacto

---

## ✅ CHECKLIST FINAL

Antes de considerar esta fase completa:

```
SPRINT 1 (Semana 1):
[ ] 5 páginas P1 creadas en Shopify
[ ] Metafields configurados
[ ] Todas sincronizadas a DB
[ ] API endpoints funcionando
[ ] Sync time < 2s
[ ] Logs sin errores

SPRINT 2 (Semana 2):
[ ] 5 páginas P2 adicionales
[ ] Total 10 páginas en sistema
[ ] Sync time < 3s
[ ] Coverage 95%

SPRINT 3 (Semana 3):
[ ] 5 páginas específicas
[ ] Total 15 páginas
[ ] Sync time < 4s
[ ] Coverage 98%

SPRINT 4 (Semana 4):
[ ] 5 páginas en inglés
[ ] Total 20 páginas
[ ] Sync time < 5s
[ ] Coverage 100%
[ ] Multi-language funcionando
```

---

**Estado actual:** 1/20 páginas (5%)
**Meta Sprint 1:** 5/20 páginas (25%)
**Meta final:** 20/20 páginas (100%)

