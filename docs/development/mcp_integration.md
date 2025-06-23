# Integración de Market Context Protocol (MCP)
incluye:

Descripción general de la integración MCP
Arquitectura y componentes principales
Endpoints API disponibles
Mercados soportados
Flujo de procesamiento conversacional
Consideraciones de implementación

## Descripción general

El Market Context Protocol (MCP) es una integración que permite al sistema de recomendaciones considerar contextos específicos de mercado y capacidades conversacionales. Esta integración permite adaptarse a diferentes mercados globales, ofreciendo recomendaciones personalizadas según la región, preferencias culturales, moneda y otros factores específicos del mercado.

## Arquitectura

La integración MCP se ha implementado siguiendo un enfoque modular que se integra con el sistema de recomendaciones existente:

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   FastAPI Principal │    │   MCP Router        │    │   ShopifyMCPClient  │
│                     │───►│                     │───►│                     │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
          │                          │                          │
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  Hybrid Recommender │    │ Market Manager      │    │   Market Cache      │
│                     │◄───│                     │◄───│                     │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

## Componentes principales

### 1. ShopifyMCPClient

Cliente para la integración con Shopify y procesamiento MCP. Proporciona:
- Procesamiento de consultas conversacionales
- Extracción de intenciones
- Obtención de productos específicos por mercado

### 2. MarketContextManager

Gestiona la configuración específica por mercado:
- Detección automática de mercado según geolocalización
- Configuración de mercados (moneda, idioma, preferencias culturales)
- Adaptación de recomendaciones según el mercado

### 3. MarketAwareProductCache

Sistema de caché que considera el contexto de mercado:
- TTL diferenciado por mercado y tipo de datos
- Invalidación selectiva por mercado
- Estrategias de pre-carga para mercados prioritarios

### 4. MCPAwareHybridRecommender

Recomendador que extiende el sistema híbrido existente con capacidades MCP:
- Adaptación de productos por mercado
- Respuestas conversacionales
- Filtrado por intenciones específicas

## Endpoints API

### Conversacionales

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/v1/mcp/conversation` | POST | Procesa consultas conversacionales y devuelve recomendaciones contextuales |
| `/v1/mcp/conversation/{session_id}/history` | GET | Obtiene el historial de una conversación |

### Mercados

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/v1/mcp/markets` | GET | Lista mercados soportados con configuraciones |
| `/v1/mcp/recommendations/{product_id}` | GET | Recomendaciones específicas por mercado para un producto |

### Caché

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/v1/mcp/cache/stats` | GET | Estadísticas del caché por mercado |
| `/v1/mcp/cache/warmup/{market_id}` | POST | Inicia pre-carga del caché para un mercado |
| `/v1/mcp/cache/invalidate/{market_id}` | POST | Invalida caché de un mercado |

## Mercados soportados

Actualmente, el sistema soporta los siguientes mercados:

| ID | Nombre | Moneda | Idioma |
|----|--------|--------|--------|
| US | Estados Unidos | USD | en |
| ES | España | EUR | es |
| MX | México | MXN | es |
| CL | Chile | CLP | es |
| default | Global | USD | en |

## Flujo de procesamiento conversacional

1. El usuario envía una consulta conversacional
2. El sistema extrae la intención y el contexto
3. Se detecta el mercado del usuario
4. Se generan recomendaciones base desde el recomendador híbrido
5. Las recomendaciones se adaptan al mercado específico
6. Se aplica filtrado basado en la intención
7. Se genera una respuesta conversacional
8. Se devuelven recomendaciones y respuesta al usuario

## Consideraciones de implementación

### Caché market-aware

El sistema implementa TTL (Time-To-Live) diferenciado según:
- Mercado (ej: mercados con alta volatilidad tienen TTL más corto)
- Tipo de datos (productos, recomendaciones, trending, disponibilidad)

### Adaptación por mercado

La adaptación incluye:
- Conversión de moneda con tasas actualizadas
- Aplicación de impuestos locales
- Ajuste de precios según convenciones del mercado
- Localización de contenido
- Filtrado por disponibilidad regional

### Análisis de intenciones

El sistema extrae las siguientes intenciones:
- `product_search`: Búsqueda específica de productos
- `recommendation`: Solicitud de recomendaciones generales
- `compare`: Comparación entre productos
- `cart_complement`: Complementos para productos en carrito
- `budget_search`: Búsqueda con restricción de presupuesto
- `gift_search`: Búsqueda de regalos
- `browse`: Navegación general
- `general`: Consultas generales

## Desarrollo futuro

- Integración con más mercados
- Mejora en la calidad de respuestas conversacionales
- Implementación de A/B testing para evaluar variantes
- Extracción gradual hacia microservicios
- Optimización de rendimiento para alta concurrencia
