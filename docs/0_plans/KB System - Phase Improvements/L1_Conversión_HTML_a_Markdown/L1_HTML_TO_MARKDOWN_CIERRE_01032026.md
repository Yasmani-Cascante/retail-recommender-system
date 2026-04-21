# L1 — Conversión HTML a Markdown: Documento de Cierre de Fase

**Sistema:** Retail Recommender System v2.1.0  
**Fase:** L1 — HTML to Markdown Library  
**Estado:** ✅ COMPLETADA Y VALIDADA  
**Fecha de cierre:** 01 de Marzo de 2026  
**Autor:** Retail Recommender System Team  

---

## 1. Resumen Ejecutivo

La Fase L1 reemplaza el parser HTML manual basado en expresiones regulares que existía en `ShopifyKBSyncService._html_to_markdown()` por una solución robusta basada en la librería **markdownify**, complementada con pre-procesado mediante **BeautifulSoup** para eliminación de ruido. La implementación preserva la estructura semántica del HTML de Shopify (headings, tablas, listas, links) en Markdown limpio y optimizado para consumo por modelos de lenguaje, mientras elimina completamente el ruido técnico habitual de las páginas Shopify (scripts de analytics, CSS inline, iframes de chat).

**Resultado:** 63 tests pasando (34 unit + 29 integration), reducción de ruido ≥40% en páginas con scripts/styles, y eliminación de un bug de producción identificado durante el desarrollo.

---

## 2. Objetivo de la Fase

### Problema original

El método `_html_to_markdown()` pre-L1 utilizaba una serie de expresiones regulares para eliminar tags HTML y extraer texto plano. Esta solución presentaba tres limitaciones estructurales:

1. **Pérdida de estructura semántica:** Las tablas HTML se convertían en texto continuo ilegible. Los headings H2/H3 perdían su jerarquía. Los links perdían sus URLs. El LLM recibía un bloque de texto en lugar de contenido organizado.

2. **Ruido no eliminado confiablemente:** Los scripts de analytics (Google Analytics, Facebook Pixel), bloques de CSS inline e iframes de widgets de chat sobrevivían parcialmente en el output, contaminando el contexto que el LLM usaba para generar respuestas.

3. **Fragilidad ante HTML real:** Las regex fallaban silenciosamente ante HTML malformado o estructuras no previstas en el momento de escribirlas, produciendo outputs inconsistentes difíciles de depurar.

### Objetivo funcional de L1

> Reemplazar el parser regex por una librería probada que produzca Markdown semánticamente correcto, eliminando ruido sin perder contenido, reduciendo el volumen de tokens y siendo resiliente ante variaciones en el HTML de Shopify.

---

## 3. Cómo Funciona la Integración

### Contexto del sistema

El sistema MCP conversacional responde preguntas de usuarios sobre políticas de la tienda (devoluciones, envíos, garantías, etc.) consultando la **Knowledge Base (KB)**, que está almacenada en PostgreSQL y sincronizada periódicamente desde las páginas de Shopify.

Cuando Shopify provee una página, su contenido viene en formato HTML (`page.body_html`). Ese HTML debe convertirse a Markdown antes de guardarse en la base de datos, porque el Markdown es el formato que el LLM procesa con mayor eficiencia.

### El flujo — analogía intuitiva

Piensa en el proceso como preparar un documento para que un asistente muy capaz pueda leerlo rápidamente:

- **HTML de Shopify** es como una página web completa con publicidad, menús, scripts ocultos y código técnico. Visualmente se ve bien, pero está llena de ruido innecesario.
- **markdownify** actúa como un editor que convierte esa página en un documento limpio de Word: mantiene los títulos como títulos, las tablas como tablas, y los links con su URL.
- **BeautifulSoup** actúa como un asistente previo que lee el documento primero y arranca físicamente las páginas con código JavaScript, CSS y iframes antes de pasárselo al editor. Sin este paso, el editor podría dejar visible el código de esas páginas aunque quitara los "envoltorios".

El resultado es un texto Markdown que el LLM puede leer como si fuera un documento bien organizado, sin distracciones técnicas.

---

## 4. Problema que Resuelve

### Antes de L1 (parser regex)

```
Input HTML (1,200 chars):
  <h2>Política de Devoluciones</h2>
  <h3>Condiciones</h3>
  <table>...</table>
  <script>gtag('event', 'page_view', {...})</script>
  <style>.return-table { border-collapse: collapse; }</style>

Output (texto plano degradado, ~900 chars):
  Política de Devoluciones Condiciones Tarjeta de crédito 5-10 días
  PayPal 3-5 días gtag event page_view page_title Política de
  Devoluciones .return-table border-collapse collapse
```

El output contiene código JavaScript y CSS visible, sin estructura, con todo el contenido fusionado en prosa continua.

### Después de L1 (markdownify + BeautifulSoup)

```
Output (Markdown estructurado, ~480 chars):
  ## Política de Devoluciones

  ### Condiciones

  | Método de Pago    | Plazo       |
  |-------------------|-------------|
  | Tarjeta de crédito| 5-10 días   |
  | PayPal            | 3-5 días    |

  [completa este formulario](https://ai-shoppings.com/contacto)
```

El output es Markdown limpio, estructurado, sin ruido, con URLs preservadas y jerarquía visual que el LLM puede razonar correctamente.

---

## 5. Funcionalidades y Capacidades

| Capacidad | Pre-L1 | Post-L1 |
|-----------|--------|---------|
| Headings H2/H3 como títulos Markdown | ❌ texto plano | ✅ `## ` y `### ` ATX |
| Tablas HTML → Markdown | ❌ texto fusionado | ✅ tabla GFM preservada |
| Links con URL | ❌ solo texto del link | ✅ `[texto](url)` completo |
| Listas ordenadas (pasos) | ❌ texto continuo | ✅ `1. 2. 3.` preservados |
| Listas no ordenadas | ❌ texto continuo | ✅ bullets con `-` |
| Eliminación de `<script>` + contenido | ⚠️ parcial | ✅ completo (decompose) |
| Eliminación de `<style>` + contenido | ⚠️ parcial | ✅ completo (decompose) |
| Eliminación de `<iframe>` | ❌ no | ✅ sí |
| Eliminación de `<noscript>` | ❌ no | ✅ sí |
| Decodificación de HTML entities | ⚠️ inconsistente | ✅ `&amp;` → `&` |
| Caracteres especiales ES (tildes, ñ) | ✅ preservados | ✅ preservados |
| Fallback ante fallo de librería | ❌ excepción | ✅ BeautifulSoup text |
| Idempotencia | ✅ | ✅ verificada |

---

## 6. Arquitectura — Componentes Principales

### Archivos modificados

```
src/api/services/shopify_kb_sync.py
├── Import nivel de módulo (líneas ~50-58)
│   ├── import markdownify as _markdownify
│   ├── _MARKDOWNIFY_AVAILABLE = True/False
│   └── Fallback silencioso si no está instalado
│
└── ShopifyKBSyncService._html_to_markdown() (líneas ~1288-1380)
    ├── Caso base: HTML vacío → ""
    ├── Guard: _MARKDOWNIFY_AVAILABLE
    ├── PRE-PROCESADO: BeautifulSoup.decompose() para tags de ruido
    ├── CONVERSIÓN: markdownify.markdownify(heading_style="ATX", bullets="-")
    └── POST-PROCESADO: re.sub(r'\n{3,}', '\n\n') + strip()
```

### Archivos de test creados/actualizados

```
tests/
├── unit/
│   └── test_kb_html_to_markdown.py       (34 tests — comportamiento del método)
└── integration/kb/
    └── test_l1_markdown_quality.py        (29 tests — calidad del output)
```

### Dependencias añadidas

```
requirements.txt:
  markdownify>=0.12.1    # Conversión HTML → Markdown
  beautifulsoup4          # Ya existía — ahora también en pre-procesado
```

---

## 7. Flujo de Datos Simplificado

```
Shopify API
    │
    │  page.body_html (HTML crudo)
    ▼
_html_to_markdown()
    │
    ├─ [1] ¿HTML vacío? → return ""
    │
    ├─ [2] ¿markdownify disponible? → No → _html_to_text_fallback()
    │
    ├─ [3] BeautifulSoup(html, "html.parser")
    │       └─ for tag in ["script","style","iframe","noscript","meta","link"]:
    │               tag.decompose()   ← elimina tag + contenido completo
    │
    ├─ [4] clean_html = str(soup)
    │
    ├─ [5] markdownify.markdownify(clean_html,
    │           heading_style="ATX",   # ## Título
    │           bullets="-"            # - ítem
    │       )
    │
    ├─ [6] re.sub(r'\n{3,}', '\n\n', markdown).strip()
    │
    └─ [7] return markdown (str, nunca None)
                │
                ▼
    _upsert_kb_content()
        │
        ▼
    PostgreSQL kb_contents.content (TEXT)
        │
        ▼
    LLM context en conversaciones MCP
```

---

## 8. Impacto en Performance y Mantenibilidad

### Performance

**Reducción de tokens (medido en caracteres como proxy):**

| Tipo de página | Reducción promedio |
|----------------|--------------------|
| Página con scripts/CSS/iframes | ≥ 40% |
| Política/FAQ sin ruido extra | ≥ 20% |

Esto se traduce directamente en menor consumo de tokens del context window del LLM por cada consulta a la KB, permitiendo incluir más contenido relevante en el mismo presupuesto de tokens.

**Overhead de procesamiento:** BeautifulSoup + markdownify añaden ~2-5ms por conversión en páginas típicas de 1-5KB. Este costo es completamente absorbido durante el proceso de sync (background job), que es asíncrono y no está en el camino crítico de las consultas de usuario.

### Mantenibilidad

La implementación anterior (regex manual) era un activo de deuda técnica: cada vez que Shopify cambiaba la estructura del HTML o se añadía un nuevo tipo de contenido, había que actualizar las regex, a menudo con efectos secundarios inesperados. La solución basada en markdownify es declarativa: convierte HTML a Markdown semánticamente, sin lógica especial por caso de uso. Los cambios en el HTML de Shopify se manejan solos.

El fallback en dos capas (markdownify → BeautifulSoup → regex) garantiza que el sistema nunca pierde contenido por un fallo en la conversión, degradando graciosamente en lugar de lanzar excepción.

---

## 9. Bug de Producción Identificado y Corregido

Durante el desarrollo de L1 (Día 2, fase de unit tests) se identificó un bug crítico en el diseño inicial de la solución:

**Síntoma:** El parámetro `strip=['script', 'style']` de markdownify eliminaba los tags HTML pero **dejaba visible el texto interno** de los scripts. Ejemplo:

```html
<script>gtag('event', 'page_view', {'page_title': 'Mi Página'})</script>
```

Con `strip=['script']` markdownify producía:
```
gtag('event', 'page_view', {'page_title': 'Mi Página'})
```

El código JavaScript era visible en el Markdown y llegaba al LLM como si fuera contenido.

**Corrección aplicada:** Pre-procesado con `BeautifulSoup.decompose()` antes de llamar a markdownify. `decompose()` elimina el tag **y todo su subárbol DOM**, incluyendo el texto. Los tags `["script", "style", "iframe", "noscript", "meta", "link"]` se eliminan con este método antes de cualquier conversión.

**Lección:** `strip=[]` en markdownify ≠ eliminar contenido. `strip` solo quita el tag wrapper. Para eliminar contenido, siempre usar `decompose()` en la etapa de pre-procesado.

---

## 10. Limitaciones Conocidas

### Tablas HTML complejas

Las tablas con celdas combinadas (`colspan`, `rowspan`) o tablas anidadas producen Markdown que puede ser difícil de parsear por algunos modelos. markdownify hace su mejor esfuerzo, pero el resultado puede no ser visualmente perfecto. Para el sistema KB actual (políticas y FAQs), las tablas simples son la norma y esta limitación no es un problema práctico.

### HTML extremadamente malformado

Si el HTML de Shopify está severamente malformado (tags sin cerrar anidados incorrectamente, encoding corrupto), BeautifulSoup puede producir un árbol DOM diferente al esperado. En estos casos extremos, el fallback `_html_to_text_fallback()` se activa y produce texto plano en lugar de Markdown estructurado — se pierde formato pero no contenido.

### Sin validación de longitud mínima del output

El sistema no tiene un umbral mínimo de longitud del Markdown resultante. Si una página de Shopify tiene contenido muy escaso (por ejemplo, una página en construcción con solo un párrafo), la KB puede tener entradas de poco valor sin ninguna advertencia.

### Cobertura de fixtures sin API real

Los tests de integración de calidad usan HTML representativo construido manualmente, no HTML extraído directamente de la API de Shopify en producción. Existe la posibilidad (pequeña) de que Shopify use estructuras HTML específicas no contempladas en los fixtures. Se mitiga con el fallback y con el diseño general-purpose de markdownify.

---

## 11. Mejoras Futuras

### L2 — Content Versioning (próxima fase)

Añadir tracking de versiones en la tabla `kb_contents` para registrar cuándo y cómo cambia el contenido. Esto permitiría detectar cuándo un re-sync produce Markdown diferente (cambio real de contenido) vs. idéntico (no hay cambio), evitando actualizaciones innecesarias de `updated_at` y reduciendo escrituras en DB.

### L3 — Multi-Region Support

Extender el sistema para que el Markdown se genere con consideraciones regionales: variantes de vocabulario ES-MX vs. ES-CL, formatos de fecha locales, monedas. Actualmente el método trata todo el español de forma uniforme.

### L4 — ML Content Optimization

Usar un modelo ligero para post-procesar el Markdown y mejorar su estructura para retrieval semántico: añadir metadatos implícitos, reescribir secciones ambiguas, generar resúmenes para documentos largos. Esta fase requeriría L2 (versionado) para no re-procesar contenido que no cambió.

### Mejora puntual — Umbral de calidad mínima

Añadir validación post-conversión que alerte (log warning) cuando el Markdown resultante es anormalmente corto en relación al HTML de entrada (posible pérdida de contenido por HTML malformado).

```python
# Ejemplo de validación propuesta
reduction_ratio = len(markdown) / len(html)
if reduction_ratio < 0.05:  # Markdown es <5% del HTML original
    logger.warning(
        "html_to_markdown_suspicious_output",
        html_length=len(html),
        markdown_length=len(markdown),
        ratio=reduction_ratio,
        note="possible_content_loss"
    )
```

---

## 12. Métricas de la Fase

| Métrica | Valor |
|---------|-------|
| Días de implementación | 2 (Día 1: setup + integración, Día 2: unit tests + bug fix + integration tests) |
| Tests unitarios creados | 34 |
| Tests de integración de calidad creados | 29 |
| Tests totales relacionados con L1 | 63 |
| Tests pasando al cierre | 63 / 63 (100%) |
| Bugs de producción encontrados | 1 (crítico, corregido en Día 2) |
| Reducción de tokens — HTML típico | ≥ 20% |
| Reducción de tokens — HTML con scripts/styles | ≥ 40% |
| Líneas de código de producción modificadas | ~50 (método `_html_to_markdown` + import) |
| Dependencias nuevas añadidas | 1 (`markdownify>=0.12.1`) |
| Breaking changes | Ninguno |
| Rollback required | No |

---

## 13. Registro de Archivos Relacionados

```
Producción:
  src/api/services/shopify_kb_sync.py         ← Implementación principal

Tests:
  tests/unit/test_kb_html_to_markdown.py       ← 34 unit tests
  tests/integration/kb/test_l1_markdown_quality.py  ← 29 integration tests

Documentación:
  docs/knowledge_base_Shopify_cms/L1_HTML_TO_MARKDOWN_CIERRE_01032026.md  ← este archivo

Dependencias:
  requirements.txt                             ← markdownify>=0.12.1 añadido
```

---

*Documento generado al cierre formal de la Fase L1. Para la siguiente fase (L2 — Content Versioning), consultar el plan en `/docs/0_plans/`.*
