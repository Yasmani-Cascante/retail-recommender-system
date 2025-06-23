# Guía para la Integración del Mercado Chile (CL)

## Descripción general

Esta guía proporciona información sobre la reciente integración del mercado de Chile (CL) en el sistema MCP y cómo trabajar con sus características específicas.

## Configuración del Mercado Chile

### Detalles básicos

- **ID de mercado**: `CL`
- **Nombre**: Chile
- **Moneda**: CLP (Peso Chileno)
- **Idioma**: es (Español)
- **Zona horaria**: America/Santiago

### Configuración específica

```json
{
    "name": "Chile",
    "currency": "CLP",
    "language": "es",
    "timezone": "America/Santiago",
    "enabled": true,
    "scoring_weights": {
        "relevance": 0.45,
        "popularity": 0.35,
        "profit_margin": 0.2
    },
    "localization": {
        "date_format": "DD/MM/YYYY",
        "cultural_preferences": {
            "size_system": "EU",
            "preferred_categories": ["fashion", "electronics", "home"],
            "seasonal_adjustments": {
                "summer": [12, 1, 2],
                "winter": [6, 7, 8]
            }
        }
    }
}
```

## Características Específicas de Chile

### Tasas de Conversión

- **USD a CLP**: 930.0
- **EUR a CLP**: 1094.0
- **MXN a CLP**: 53.0

### Impuestos

- **IVA**: 19% (implementado como factor 0.19)

### Convenciones de Precios

Los precios en Chile típicamente siguen el patrón de terminar en "990":
- Precios bajos terminan en 990 (ejemplo: 1.990 CLP)
- Precios medios y altos suelen terminar en 990 (ejemplo: 10.990 CLP, 100.990 CLP)

### Estacionalidad Invertida

Chile, al estar en el hemisferio sur, tiene estaciones invertidas respecto al hemisferio norte:
- **Verano**: Diciembre, Enero, Febrero
- **Invierno**: Junio, Julio, Agosto

Esta información está configurada en `seasonal_adjustments` y debe considerarse para recomendaciones de productos estacionales.

## Uso en APIs

### Ejemplo de Request para Conversación

```json
POST /v1/mcp/conversation
{
    "query": "Busco un notebook gamer",
    "user_id": "user123",
    "market_id": "CL",
    "language": "es",
    "n_recommendations": 5
}
```

### Ejemplo de Request para Recomendaciones por Producto

```
GET /v1/mcp/recommendations/product123?market_id=CL&n=5
```

## Adaptaciones en Frontend

Para trabajar con el mercado chileno en frontend, considerar:

### Formato de Moneda

```javascript
// Formateo de moneda CLP (sin decimales)
function formatCLPPrice(price) {
    return new Intl.NumberFormat('es-CL', {
        style: 'currency',
        currency: 'CLP',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(price);
}

// Ejemplo: 10990 → "$10.990"
```

### Terminología Específica

Algunos términos utilizados en Chile que difieren de otros mercados hispanohablantes:

| Término España | Término México | Término Chile |
|----------------|----------------|---------------|
| Ordenador | Computadora | Computador |
| Móvil | Celular | Celular |
| Zapatillas deportivas | Tenis | Zapatillas |
| Camiseta | Playera | Polera |
| Cazadora | Chamarra | Chaqueta |

## Consideraciones para Testing

Al probar funcionalidades para el mercado chileno:

1. **Verificar conversión de moneda**: Asegurar que los precios se convierten correctamente a CLP
2. **Comprobar formato de precios**: Validar que los precios siguen la convención chilena (terminados en 990)
3. **Probar adaptación estacional**: Verificar que las recomendaciones consideran la estacionalidad invertida
4. **Validar terminología**: Asegurar que las respuestas conversacionales utilizan terminología chilena

## Métricas de Caché

Las configuraciones de TTL para el mercado chileno son:

- **Productos**: 4500 segundos (1.25 horas)
- **Recomendaciones**: 2400 segundos (40 minutos)
- **Trending**: 1200 segundos (20 minutos)
- **Disponibilidad**: 400 segundos (6.5 minutos)

## Próximos Pasos

Para mejorar la integración del mercado chileno:

1. **Datos regionales**: Incorporar datos específicos de regiones chilenas para mejorar recomendaciones
2. **Términos de búsqueda locales**: Añadir mapeo de términos de búsqueda específicos chilenos
3. **Fechas importantes**: Configurar fechas comerciales importantes específicas de Chile
4. **Proveedores locales**: Integrar con proveedores de datos locales chilenos

## Contactos para Soporte

Para consultas específicas sobre la integración del mercado chileno, contactar:
- Equipo de Localización: localization@example.com
- Equipo MCP: mcp-support@example.com
