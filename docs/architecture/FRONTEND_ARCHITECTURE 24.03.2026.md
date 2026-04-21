# Arquitectura Frontend — Retail Recommender Widget
## Referencia técnica para desarrolladores

**Versión:** 1.0.0  
**Última actualización:** 24/03/2026  
**Sistema:** Retail Recommender System v2.1.0

---

## Visión general

El frontend es un **widget conversacional embebible** construido con React 18 + TypeScript que se despliega en Shopify (o cualquier sitio web) como un único archivo JavaScript autocontenido. El widget abre un panel de chat donde el usuario puede hacer preguntas sobre productos, políticas y disponibilidad, y recibe respuestas del backend MCP de recomendaciones.

El diseño sigue el patrón establecido por Intercom, Crisp y HubSpot: un único fichero `.cjs` que incluye todo (JS + CSS), que se inyecta en la página host sin ninguna dependencia externa ni hoja de estilos separada.

---

## Estructura de archivos

```
src/frontend/
├── index.html                      ← Página dev local (réplica de AI-Shoppings)
├── vite.config.ts                  ← Build config: modo librería UMD + CSS embebido
├── tailwind.config.js              ← Config de Tailwind (prefijo rr-, actualmente sin uso en componentes)
├── postcss.config.js               ← PostCSS con autoprefixer
├── tsconfig.json
├── package.json
└── src/
    ├── main.tsx                    ← Entry point: WidgetManager + API global window.*
    ├── vite-env.d.ts
    ├── types/
    │   └── widget.ts               ← Interfaces TypeScript (WidgetConfig, Message, etc.)
    ├── services/
    │   └── api.ts                  ← ConversationAPI: comunicación con el backend
    ├── styles/
    │   └── main.css                ← Animaciones globales (keyframes) + scrollbar
    └── components/
        ├── ChatWidget.tsx          ← Componente raíz: panel completo del chat
        ├── ChatWidget.module.css   ← Estilos del panel
        ├── ChatBubble.tsx          ← Botón flotante
        ├── ChatBubble.module.css   ← Estilos del botón
        ├── MessageList.tsx         ← Lista de mensajes + indicador de escritura
        ├── MessageList.module.css
        ├── MessageInput.tsx        ← Input de texto + botón enviar
        ├── MessageInput.module.css
        ├── ProductCard.tsx         ← Tarjeta de producto recomendado
        └── ProductCard.module.css

static/widget/                      ← Output del build — servido por FastAPI
├── embed.js                        ← Script de inicialización para Shopify
├── widget.umd.cjs                  ← Bundle completo (JS + CSS inline, ~150KB)
└── widget.umd.cjs.map              ← Source map para debugging
```

---

## Sistema de estilos — CSS Modules + inyección automática

### Por qué CSS Modules y no Tailwind

Durante el desarrollo inicial los componentes usaban clases de Tailwind con prefijo `rr-` (ej: `rr-fixed rr-bottom-4 rr-right-4`). Este enfoque fallaba en producción porque Vite en modo `lib` genera `style.css` como archivo separado que nunca se carga en Shopify.

**Solución implementada (23/03/2026):**

1. **CSS Modules** para estilos de componentes — Vite genera nombres con hash únicos (ej: `_bubble_a7f3k`) que nunca colisionan con el CSS de Shopify ni de ningún otro sitio host.

2. **`vite-plugin-css-injected-by-js`** — convierte todo el CSS compilado en un string literal e inyecta un `<style>` tag en el `<head>` del documento host cuando el bundle se carga. No se necesita ningún archivo CSS externo.

3. **Animaciones en `main.css`** — los keyframes (`@keyframes rrSlideUp`, `@keyframes rrBounce`) no pueden definirse inline en los componentes React, por eso viven en `main.css`. Este archivo también es procesado por `vite-plugin-css-injected-by-js`.

**Flujo de estilos en producción:**

```
npm run build
  ↓
Vite compila todos los .module.css y main.css
  ↓
vite-plugin-css-injected-by-js inyecta el CSS como string en widget.umd.cjs
  ↓
Shopify carga widget.umd.cjs
  ↓
Primera línea ejecutada: document.head.appendChild(<style>...todo el CSS...</style>)
  ↓
El widget se renderiza con todos sus estilos correctos
```

### Paleta de colores y tokens visuales

Los tokens de diseño están definidos directamente en los CSS Modules (no en variables CSS globales, para evitar colisiones con el host):

| Token | Valor | Uso |
|---|---|---|
| Negro principal | `#1c1c1c` | Header, bordes, texto |
| Fondo panel | `#ffffff` | Panel de chat |
| Fondo mensajes | `#f8f7f5` | Área de mensajes |
| Acento cálido | `#f3ede6` / `#e8ddd4` | Avatar, placeholders de imagen |
| Bordes sutiles | `rgba(0,0,0,0.06)` | Separadores |
| Error | `#ef4444` | Badge, mensajes de error |
| Verde status | `#4ade80` | Indicador "En línea" |

### Regla crítica — `position: fixed` en el contenedor

El contenedor raíz del widget (`#retail-recommender-widget`) **nunca debe tener** `position: relative`. Cualquier elemento con `position: relative` o `position: absolute` en la cadena de ancestros de un hijo `fixed` actúa como nuevo stacking context y hace que el `fixed` del hijo se comporte como `absolute`, rompiendo el posicionamiento.

```html
<!-- CORRECTO: contenedor es un portal transparente -->
<div id="retail-recommender-widget"
     style="position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none; z-index: 9999;">
  <!-- ChatBubble usa position: fixed internamente -->
  <!-- Sus hijos se posicionan relativos al viewport, no al contenedor -->
</div>
```

---

## Componentes

### `main.tsx` — Entry point y API global

Expone `window.RetailRecommenderWidget` con cuatro métodos:

```typescript
window.RetailRecommenderWidget = {
  init(config: WidgetConfig & { containerId?: string }): void
  destroy(): void
  show(): void
  hide(): void
}
```

**Lógica de `init()`:**
1. Valida que `apiUrl` y `apiKey` estén presentes.
2. Crea un `<div id="retail-recommender-widget">` con `position: fixed` y `pointer-events: none`, y lo añade al `<body>`.
3. Monta React con `createRoot().render(<ChatWidget />)`.
4. El wrapper inmediato del `ChatWidget` tiene `pointer-events: auto` para que los clicks lleguen al widget.

**Auto-inicialización:** Al `DOMContentLoaded`, busca `<script data-auto-init>` o `<script data-rr-auto-init>` en el DOM y llama a `init()` con los atributos `data-api-url`, `data-api-key`, `data-market-id`, `data-theme`.

---

### `ChatWidget.tsx` — Componente raíz

Gestiona el estado completo de la conversación:

```typescript
interface ConversationState {
  sessionId: string
  messages: Message[]
  isLoading: boolean
  isMinimized: boolean
}
```

**Estado `isOpen`:** separado del `ConversationState` porque no necesita persistencia en Redis.

**Flujo de un mensaje:**
1. Usuario escribe y envía → `handleSendMessage(text)`
2. Se añade `Message{type:'user'}` al estado inmediatamente (feedback visual)
3. `isLoading: true` activa el indicador de escritura (tres puntos)
4. `api.sendMessage(text)` hace el POST al backend
5. Respuesta → `Message{type:'assistant', recommendations:[...]}` se añade al estado
6. `isLoading: false`

**Mensaje de bienvenida:** se añade en `useEffect([], [])` al montar el componente. No viene del backend.

---

### `ChatBubble.tsx` — Botón flotante

Renderiza `null` cuando `isOpen && !isMinimized` (el botón se oculta cuando el panel está abierto).

Usa `position: fixed` vía CSS Module — no Tailwind. Posición: `bottom: 6vh`, `right: 0px`.

El icono SVG es el de una burbuja de chat con un símbolo de destellos en la esquina superior, inline en el JSX. No depende de lucide-react.

---

### `MessageList.tsx` — Lista de mensajes

Cada mensaje tiene una burbuja con `border-radius` asimétrico (estilo iMessage):
- Mensajes de usuario: `18px 18px 4px 18px` — esquina inferior derecha recta
- Mensajes del asistente: `18px 18px 18px 4px` — esquina inferior izquierda recta

El asistente tiene un avatar `✨` a la izquierda de cada mensaje.

Las recomendaciones de productos se renderizan debajo del texto del mensaje como lista de `<ProductCard>`.

Auto-scroll al último mensaje con `scrollIntoView({ behavior: 'smooth' })`.

---

### `MessageInput.tsx` — Input de texto

Textarea autoexpandible (altura calculada con `scrollHeight`) con máximo de 100px.

El botón "enviar" tiene dos estados visuales: activo (fondo oscuro) y deshabilitado (fondo gris) — controlados por className condicional del CSS Module.

`Enter` envía el mensaje. `Shift+Enter` inserta salto de línea.

---

### `ProductCard.tsx` — Tarjeta de producto

Renderiza título, descripción (max 2 líneas), precio formateado con `Intl.NumberFormat` y porcentaje de "match" del score.

Si `imageUrl` está disponible: muestra la imagen. Si no: muestra `🛍️` como placeholder.

**TODO pendiente:** El campo `url` para navegar a la página del producto existe en el modelo pero no siempre viene en la respuesta del backend. Cuando esté disponible, la tarjeta debe abrir la URL en nueva pestaña.

---

### `api.ts` — ConversationAPI

Clase que encapsula toda la comunicación con el backend.

**Gestión de identidad:**
- `sessionId`: generado al instanciar la clase — `widget_session_{timestamp}_{random}`. Se sincroniza con el `session_id` retornado por el backend después del primer mensaje.
- `userId`: persistido en `localStorage` con clave `rr_widget_user_id`. Si localStorage no está disponible (modo incógnito, etc.), genera un ID temporal por sesión.

**Request al backend:**
```
POST /v1/mcp/conversation
Headers:
  Content-Type: application/json
  X-API-Key: {apiKey}
  Accept-Language: {navigator.language}
  X-Widget-Version: 1.0.0

Body:
  query: string
  user_id: string
  session_id: string
  market_id: string
  language: string               ← primeros 2 chars de navigator.language
  widget_context:
    page_url: string             ← window.location.href
    page_type: string            ← product|category|cart|checkout|search|general
    product_id?: string          ← extraído de URL o meta tags
    user_agent: string
```

**Detección de tipo de página:** método `detectPageType()` analiza `window.location.pathname` para clasificar la página actual:

| Path contiene | Tipo retornado |
|---|---|
| `/products/` o `/product/` | `product` |
| `/collections/` o `/category/` | `category` |
| `/cart` | `cart` |
| `/checkout` | `checkout` |
| `/search` | `search` |
| Cualquier otro | `general` |

**Extracción de product_id:** método `extractProductId()` busca en este orden: URL path (`/products/{id}`), meta tag `product:retailer_item_id`, atributo `data-product-id`.

**Manejo de errores diferenciado (fix 23/03/2026):**

Los errores HTTP usan el prefijo `HTTP_NNN:` para distinguirlos de errores de red:

```typescript
// Errores de servidor (4xx, 5xx)
throw new Error(`HTTP_${response.status}:${errorDetail}`)

// Captura y clasificación:
if (errorMessage.startsWith('HTTP_')) {
  const code = errorMessage.split(':')[0].replace('HTTP_', '');
  // 401/403 → "Error de autenticación"
  // 429     → "Demasiadas solicitudes"
  // 5xx     → "El servidor encontró un error"
} else if (errorMessage.includes('failed to fetch')) {
  // Error genuino de red sin conexión al servidor
}
```

---

## Build y despliegue

### Flujo completo

```
src/frontend/          ← código fuente TypeScript/React
    ↓ npm run build
static/widget/         ← output del build
    widget.umd.cjs     ← bundle autocontenido (~150KB, incluye CSS)
    embed.js           ← script de inicialización (no se regenera en build)
    ↓ Dockerfile.cloudrun: COPY static/ /app/static/
/app/static/widget/    ← en el contenedor Cloud Run
    ↓ FastAPI: app.mount("/static", StaticFiles(directory="static"))
https://.../static/widget/widget.umd.cjs   ← servido por el backend
```

### Comandos

```bash
# Desarrollo local (hot-reload, sin deploy)
cd src/frontend
npm install
npm run dev          # http://localhost:5173

# Build de producción
npm run build        # genera static/widget/widget.umd.cjs

# Deploy completo (build incluido automáticamente via Dockerfile)
cd ../..
gcloud run deploy retail-recommender \
  --source . \
  --region us-central1 \
  --project retail-recommendations-449216
```

### Verificación post-deploy

```bash
curl -I https://retail-recommender-lzf2y6pspa-uc.a.run.app/static/widget/widget.umd.cjs
# → HTTP/1.1 200 OK, Content-Type: application/javascript

curl -I https://retail-recommender-lzf2y6pspa-uc.a.run.app/static/widget/embed.js
# → HTTP/1.1 200 OK
```

---

## Integración en Shopify

### Snippet actual en `theme.liquid`

```html
<!-- Retail Recommender Widget -->
<script
  src="https://retail-recommender-lzf2y6pspa-uc.a.run.app/static/widget/embed.js"
  data-auto-init
  data-api-url="https://retail-recommender-lzf2y6pspa-uc.a.run.app"
  data-api-key="2fed9999056fab6dac5654238f0cae1c"
  data-market-id="ES"
  data-theme="light">
</script>
```

### Cómo funciona `embed.js`

1. Se carga como `<script>` en el HTML de Shopify.
2. Al `DOMContentLoaded`, detecta su propio `data-auto-init` o `data-rr-auto-init`.
3. Llama a `loadWidget()` que inyecta dinámicamente `widget.umd.cjs` en el `<head>`.
4. Cuando `widget.umd.cjs` carga, expone `window.RetailRecommenderWidget`.
5. `embed.js` llama a `window.RetailRecommenderWidget.init(config)`.

Este doble-carga (embed → widget) permite actualizar el widget en el backend sin cambiar el snippet de Shopify.

### Atributos de configuración del script

| Atributo | Requerido | Descripción |
|---|---|---|
| `data-auto-init` | Sí | Activa la inicialización automática |
| `data-api-url` | Sí | URL base del backend |
| `data-api-key` | Sí | API key de autenticación |
| `data-market-id` | No | Mercado (default: `US`) |
| `data-theme` | No | Tema visual (default: `light`) |

### Inicialización manual (sin embed.js)

Para proyectos que no usan Shopify o necesitan control manual:

```html
<script src="https://.../static/widget/widget.umd.cjs"></script>
<script>
  window.RetailRecommenderWidget.init({
    apiUrl: 'https://retail-recommender-lzf2y6pspa-uc.a.run.app',
    apiKey: '2fed9999056fab6dac5654238f0cae1c',
    marketId: 'ES',
    theme: 'light',
  });
</script>
```

---

## Entorno de desarrollo local

El `index.html` es una réplica funcional de la tienda `ai-shoppings.myshopify.com` con header, hero, grid de 6 productos de moda y footer. Incluye un panel de desarrollo flotante (esquina superior izquierda).

### Tres modos de desarrollo

| Modo | Cuándo usarlo | Backend |
|---|---|---|
| **Mock** (default) | UI/UX puro, sin backend | Respuestas simuladas en `index.html` |
| **Local API** | Backend corriendo con `uvicorn` | `http://localhost:8000` |
| **Cloud Run** | Probar contra producción real | URL de Cloud Run |

En modo **Mock**, el `index.html` instala un interceptor global de `fetch` que responde a `/v1/mcp/conversation` con datos simulados sin tocar el backend. Latencia simulada de 800-1400ms para realismo.

Los tres modos son seleccionables en tiempo real desde el panel, sin recargar la página.

---

## Tipos TypeScript

### `WidgetConfig`

```typescript
interface WidgetConfig {
  apiUrl: string           // URL base del backend (requerido)
  apiKey: string           // X-API-Key (requerido)
  marketId?: string        // 'US' | 'ES' | 'MX' | 'CL' (default: 'US')
  theme?: 'light' | 'dark' | 'auto'  // Tema visual (default: 'light')
  position?: 'bottom-right' | 'bottom-left' | 'center'
  primaryColor?: string    // Color principal (no implementado todavía)
  language?: string        // ISO code — se auto-detecta de navigator.language
}
```

### `Message`

```typescript
interface Message {
  id: string
  type: 'user' | 'assistant' | 'system' | 'error'
  content: string
  timestamp: number        // Unix ms
  recommendations?: ProductRecommendation[]
  metadata?: {
    sessionId?: string
    intentAnalysis?: any
    marketContext?: any
  }
}
```

### `ProductRecommendation`

```typescript
interface ProductRecommendation {
  id: string
  title: string
  description: string
  price: number
  category: string
  score: number            // 0.0-1.0 — porcentaje de match
  imageUrl?: string        // URL de imagen del producto
  // TODO: url?: string    ← pendiente de implementar en backend + ProductCard
}
```

---

## Deuda técnica conocida

| Issue | Impacto | Prioridad |
|---|---|---|
| Campo `url` en `ProductRecommendation` | ProductCard no puede navegar a página del producto | Media |
| Moneda hardcodeada en ProductCard | Precios en mercados no-EUR pueden mostrarse incorrectamente | Media |
| Tema `dark` y `auto` no implementados | Solo funciona `light` | Baja |
| `primaryColor` en `WidgetConfig` no conectado | Customización de color no disponible | Baja |
| `position: 'bottom-left'` no implementado | Solo bottom-right funciona | Baja |
| Tests unitarios de componentes | No existen tests de UI | Media |
| `tailwindcss` en dependencias sin uso real | Dependencia muerta que añade peso al dev | Baja |

---

## Dependencias del build

| Paquete | Versión | Rol |
|---|---|---|
| `react` + `react-dom` | 18.2.0 | Framework UI |
| `vite` | 8.0.2 | Build tool y dev server |
| `@vitejs/plugin-react` | 4.6.0 | Soporte JSX/TSX en Vite |
| `vite-plugin-css-injected-by-js` | 3.5.2 | **Crítico** — CSS inline en bundle para Shopify |
| `typescript` | 5.0.2 | Tipado estático |
| `tailwindcss` | 3.3.3 | Instalado, no usado activamente en componentes |
| `lucide-react` | 0.263.1 | Iconos SVG (no usado desde 23/03/2026) |
| `clsx` | 2.0.0 | Utilidad classNames (no usado activamente) |
| `terser` | 5.44.0 | Minificación del bundle de producción |

---

## Guía para cambios futuros

### Añadir un nuevo componente

1. Crear `NombreComponente.tsx` en `src/frontend/src/components/`
2. Crear `NombreComponente.module.css` junto al componente con todos sus estilos
3. No usar Tailwind ni `style={{}}` inline — usar exclusivamente CSS Modules
4. Importar desde `ChatWidget.tsx` si se integra en el panel principal
5. Ejecutar `npm run dev` para verificar visualmente con los tres modos
6. Ejecutar `npm run build` y confirmar que `static/widget/widget.umd.cjs` se regenera

### Modificar el contrato de la API

El único punto de integración con el backend es `src/frontend/src/services/api.ts`.
- Cambios en el request: modificar la interfaz `ConversationRequest` y el cuerpo del `fetch`
- Cambios en la respuesta: modificar la interfaz `ConversationResponse` y el mapeo a `Message`
- Cambios en los tipos de producto: modificar `ProductRecommendation` en `widget.ts`

### Cambiar el estilo visual del botón flotante

Editar `ChatBubble.module.css`:
```css
.bubble {
  background: rgba(255,255,255, 0.85);  /* ← fondo en reposo */
  color: #1c1c1c;                        /* ← color del icono */
  border: 2px solid #1c1c1c;
}
.bubble:hover {
  background: rgba(28, 28, 28, 1);      /* ← fondo en hover */
  color: #ffffff;
}
```
Reconstruir con `npm run build` y redesplegar.

### Añadir soporte de tema oscuro

1. Definir variables CSS en `main.css` bajo `@media (prefers-color-scheme: dark)`
2. Reemplazar colores hardcodeados en los CSS Modules por `var(--rr-*)` con fallback
3. Añadir lógica de detección en `main.tsx` cuando `theme === 'auto'`

---

*Documento de referencia — Retail Recommender System v2.1.0*  
*Generado: 24/03/2026*
