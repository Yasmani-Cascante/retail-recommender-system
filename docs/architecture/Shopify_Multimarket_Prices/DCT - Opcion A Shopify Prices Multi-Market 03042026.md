# DCT — Opcion A Shopify Prices Multi-Market — 28/03/2026

**Fecha:** 28/03/2026  

**Estado:** Implementacion completada, pendiente deploy y validacion

---

## Contexto del problema resuelto

El sistema mostraba precios incorrectos en el mensaje de Claude:

- Shopify Admin: precio = 160.000 CLP
- ProductCard: CHF 159.00 (correcto)
- Claude decia: "160.000,00 EUR" (precio CLP crudo con moneda incorrecta)

**Causa raiz:** El catalogo TF-IDF almacenaba el precio CLP crudo (via REST API). El MarketAdapter lo convertia en FASE 5, pero Claude construia su prompt en FASE 3 (antes de la conversion). Las tasas de conversion eran hardcodeadas en 3 lugares.

---

## Descubrimiento clave: 4 mercados activos en Shopify

La tienda AI-Shoppings tiene 4 mercados activos confirmados en Shopify Admin:

| Mercado | Pais | Moneda |
| --- | --- | --- |
| Chile | CL | CLP (nativa) |
| Switzerland | CH | CHF |
| Mexico | MX | MXN |
| International | 27 regiones | USD |

---

## Archivos modificados

### 1. `src/api/integrations/shopify_client.py` (REESCRITO, 25.22 KB)

Nuevo metodo `get_products_with_shopify_prices()`:

- REST obtiene lista de productos
- GraphQL `contextualPricing` obtiene precio por mercado en lotes de 30
- Enriquece cada producto con `market_prices`:

```python
product["market_prices"] = {
  "CL": {"price": 160000.0, "currency": "CLP"},
  "CH": {"price": 159.0,    "currency": "CHF"},
  "MX": {"price": 3200.0,   "currency": "MXN"},
  "US": {"price": 166.4,    "currency": "USD"}
}
```

Usa el mismo Admin Access Token. Endpoint `/admin/api/2025-01/graphql.json`.

### 2. `src/api/main_unified_redis.py`

`load_shopify_products()` ahora llama `get_products_with_shopify_prices()` en lugar de `get_products()`.

Doble fallback: si GraphQL falla -> REST; si REST falla -> datos de muestra.

### 3. `src/api/mcp/engines/mcp_personalization_engine.py`

`_build_advanced_personalization_prompt()`: nueva funcion `_get_price_for_prompt(rec, market_id, currency)`.

Prioridad:

1. `market_prices[market_id]` <- precio Shopify para el mercado del cliente
2. `market_prices["CL"]` <- fallback precio nativo CLP
3. Conversion manual hardcodeada <- ultimo recurso (compatibilidad)

---

## Pendiente para la proxima sesion

1. MCP server local estaba no responsivo al final de la sesion - verificar antes de continuar
2. Deploy a Cloud Run con los 3 archivos modificados
3. Verificar en GCP Logs: `[ShopifyPrices] Enrichment complete:` - confirma GraphQL funciono
4. Test: cliente suizo debe ver CHF 159.00 en el chat (no EUR 160.000)
5. Fase futura: actualizar MarketAdapter para leer `market_prices` y eliminar tasas hardcodeadas restantes

---

## Deuda tecnica restante

`MarketAdapter` aun usa conversion hardcodeada para la ProductCard. El adapter necesita actualizarse para leer `market_prices` del producto, lo que eliminaria todas las tasas hardcodeadas del sistema.