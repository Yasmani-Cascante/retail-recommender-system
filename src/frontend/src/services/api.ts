import type { WidgetConfig, Message, ProductRecommendation } from '../types/widget';

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS — defensive normalization of backend responses
// ─────────────────────────────────────────────────────────────────────────────

/**
 * extractAnswer
 *
 * The backend has multiple execution paths (transactional, informational,
 * greeting, diversification, personalisation, fallback). Each path can return
 * the text answer in a different shape:
 *   • string                          → return as-is
 *   • { response: string }            → MCPPersonalisationEngine raw dict
 *   • { response: { content: ... } }  → nested dict
 *   • { answer: string }              → router early-return
 *   • { content: string }             → Anthropic SDK object
 *   • anything else                   → JSON.stringify as last resort
 *
 * This function is the last line of defence on the client side so that nothing
 * ever reaches the chat bubble as "[object Object]" or raw JSON.
 */
function extractAnswer(raw: unknown): string {
  if (typeof raw === 'string') return raw;

  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;

    // MCPPersonalisationEngine returns { response: string | dict, ... }
    if ('response' in obj) {
      const r = obj.response;
      if (typeof r === 'string') return r;
      if (r && typeof r === 'object') {
        const inner = r as Record<string, unknown>;
        for (const key of ['content', 'text', 'message', 'answer']) {
          if (typeof inner[key] === 'string') return inner[key] as string;
        }
        return JSON.stringify(r);
      }
    }

    // Router early-return informational / greeting path
    if ('answer' in obj && typeof obj.answer === 'string') return obj.answer;

    // Anthropic SDK ContentBlock
    if ('content' in obj && typeof obj.content === 'string') return obj.content as string;
    if ('text' in obj && typeof obj.text === 'string') return obj.text as string;
    if ('message' in obj && typeof obj.message === 'string') return obj.message as string;

    return JSON.stringify(raw);
  }

  return String(raw ?? '');
}

/**
 * stripHtml
 *
 * Product descriptions in Shopify are stored as rich HTML and come through
 * the backend without stripping.  Rendering raw HTML as text in React
 * (`{product.description}`) shows "<span style=...>text</span>" literally.
 *
 * We strip tags client-side using a temporary DOM element (safe — no
 * script execution, just text extraction).  Falls back to a regex approach
 * in environments where document is unavailable (SSR / tests).
 */
function stripHtml(html: string): string {
  if (!html) return '';
  try {
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return (tmp.textContent ?? tmp.innerText ?? '').trim();
  } catch {
    // Fallback for non-browser environments
    return html.replace(/<[^>]*>/g, '').trim();
  }
}

/**
 * normalizeRecommendation
 *
 * Each backend path (HybridRecommender, diversification, fallback, market
 * adaptation) can return a recommendation with slightly different field names
 * and types.  Normalise to the canonical ProductRecommendation shape that
 * the UI components expect, with safe defaults for every field.
 *
 * Key invariants:
 *   • price       — always a finite number ≥ 0  (missing or NaN → 0)
 *   • description — HTML stripped, max 200 chars
 *   • score       — clamped to [0, 1]
 *   • id / title  — always a non-empty string
 */
function normalizeRecommendation(raw: Record<string, unknown>): ProductRecommendation {
  // Some paths nest the product data under a "product" key
  const src: Record<string, unknown> =
    raw.product && typeof raw.product === 'object'
      ? {
          ...(raw.product as Record<string, unknown>),
          // Lift score / currency from the outer wrapper if not present inside
          score: (raw.product as Record<string, unknown>).score ?? raw.score ?? raw.market_score,
          currency:
            (raw.product as Record<string, unknown>).currency ??
            raw.currency,
        }
      : raw;

  // Price — accept price or market_price; guard against undefined / NaN
  const rawPrice = src.price ?? src.market_price;
  const price =
    typeof rawPrice === 'number' && isFinite(rawPrice) && rawPrice >= 0
      ? rawPrice
      : 0;

  // Score — accept any score-like field; clamp to [0, 1]
  const rawScore =
    src.score ?? src.market_score ?? src.similarity_score ?? src.viability_score;
  const score =
    typeof rawScore === 'number' && isFinite(rawScore)
      ? Math.min(1, Math.max(0, rawScore))
      : 0;

  // Description — strip HTML tags, truncate
  const rawDesc = (src.description as string) ?? '';
  const description = stripHtml(rawDesc).slice(0, 200);

  // Image URL — accept image_url, imageUrl, or first element of images[]
  let image_url: string | undefined;
  if (typeof src.image_url === 'string' && src.image_url) {
    image_url = src.image_url;
  } else if (typeof src.imageUrl === 'string' && src.imageUrl) {
    image_url = src.imageUrl;
  } else if (Array.isArray(src.images) && src.images.length > 0) {
    image_url = String(src.images[0]);
  }

  return {
    id:          String(src.id ?? 'unknown'),
    title:       String(src.title ?? src.localized_title ?? 'Producto'),
    description,
    price,
    currency:    String(src.currency ?? 'EUR'),
    category:    String(src.category ?? src.product_type ?? ''),
    score,
    image_url,
    url:         typeof src.url === 'string' && src.url ? src.url : undefined,
  };
}

// ─────────────────────────────────────────────────────────────────────────────

interface ConversationRequest {
  query: string;
  user_id?: string;
  session_id?: string;
  market_id?: string;
  language: string;
  widget_context?: {
    page_url: string;
    page_type: string;
    product_id?: string;
    user_agent: string;
    // F-04: ID del cliente Shopify logueado. Undefined para usuarios anónimos.
    customer_id?: string;
  };
}

interface ConversationResponse {
  answer: unknown;           // typed as unknown — we always pass through extractAnswer()
  recommendations: unknown[];
  kb_document?: string;
  session_metadata: {
    session_id: string;
    user_id: string;
  };
  intent_analysis?: unknown;
  market_context?: unknown;
  personalization_metadata?: unknown;
  metadata?: unknown;
  took_ms?: number;
}

export class ConversationAPI {
  private config: WidgetConfig;
  private sessionId: string;
  private userId: string;

  constructor(config: WidgetConfig) {
    this.config = config;
    this.sessionId = this.generateSessionId();
    this.userId = this.generateUserId();
  }

  async sendMessage(message: string, productHandle?: string): Promise<Message> {
    try {
      const request: ConversationRequest = {
        query: message,
        user_id: this.userId,
        session_id: this.sessionId,
        market_id: this.config.marketId || 'US',
        language: navigator.language.split('-')[0],
        widget_context: {
          page_url: window.location.href,
          page_type: this.detectPageType(),
          // Si hay un producto activo seleccionado por el usuario (chip de contexto),
          // usamos su handle como product_id en lugar del de la URL actual.
          // Esto hace que el backend base las recomendaciones en ese producto
          // específico en lugar del producto de la página.
          product_id: productHandle ?? this.extractProductId(),
          user_agent: navigator.userAgent,
          // F-04: propagar el customer_id al backend para enriquecimiento
          // del perfil de cliente. Undefined si el usuario no está logueado.
          customer_id: this.config.customerId || undefined,
        }
      };

      const response = await fetch(`${this.config.apiUrl}/v1/mcp/conversation`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.config.apiKey,
          'Accept-Language': navigator.language || 'en-US',
          'X-Widget-Version': '1.0.0',
        },
        body: JSON.stringify(request),
      });

      // FIX (23/03/2026): Raise differentiated HTTP errors.
      // Prefix HTTP_NNN: so the catch block can distinguish them from
      // genuine network failures (TypeError: failed to fetch).
      if (!response.ok) {
        let errorDetail = '';
        try {
          const errBody = await response.json();
          errorDetail = errBody.detail || errBody.message || '';
        } catch {
          // Body is not JSON — continue without detail
        }
        throw new Error(`HTTP_${response.status}:${errorDetail}`);
      }

      const data: ConversationResponse = await response.json();

      // Sync the session ID returned by the backend.
      // syncSessionFromBackend() actualiza this.sessionId Y localStorage
      // con el valor canónico del servidor, garantizando continuidad multi-turno
      // y persistencia entre recargas de página (F-07 / Paso 3).
      if (
        data.session_metadata &&
        typeof data.session_metadata === 'object' &&
        'session_id' in data.session_metadata &&
        typeof data.session_metadata.session_id === 'string'
      ) {
        this.syncSessionFromBackend(data.session_metadata.session_id);
      }

      // ── FIX (27/03/2026): Normalize the answer field.
      // The backend has at least 5 different execution paths that can each
      // return the answer in a different shape (string, dict with 'response',
      // dict with 'answer', Anthropic SDK object, raw JSON, …).
      // extractAnswer() handles every known case and falls back gracefully.
      const answerText = extractAnswer(data.answer);

      // ── FIX (27/03/2026): Normalize recommendations array.
      // Each backend path (HybridRecommender, diversification, market
      // adaptation, fallback) can emit slightly different field names.
      // normalizeRecommendation() maps them to the canonical shape and
      // strips HTML from description, coerces price to a number, etc.
      const rawRecs = Array.isArray(data.recommendations) ? data.recommendations : [];
      const recommendations: ProductRecommendation[] = rawRecs
        .filter((r): r is Record<string, unknown> => r != null && typeof r === 'object')
        .map(normalizeRecommendation);

      return {
        id:              this.generateMessageId(),
        type:            'assistant',
        content:         answerText,
        timestamp:       Date.now(),
        recommendations,
        kb_document:     data.kb_document,
        metadata: {
          sessionId:     this.sessionId,
          intentAnalysis: data.intent_analysis,
          marketContext:  data.market_context,
        },
      };

    } catch (error) {
      console.error('Widget API Error:', error);

      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      let friendlyMessage = 'Lo siento, ha ocurrido un error. Por favor intenta de nuevo.';

      // FIX (23/03/2026): Differentiate HTTP errors from genuine network errors.
      if (errorMessage.startsWith('HTTP_')) {
        const code = errorMessage.split(':')[0].replace('HTTP_', '');
        if (code === '401' || code === '403') {
          friendlyMessage = 'Error de autenticación. Por favor contacta con soporte.';
        } else if (code === '429') {
          friendlyMessage = 'Demasiadas solicitudes. Por favor espera un momento.';
        } else if (code.startsWith('5')) {
          friendlyMessage = 'El servidor encontró un error. Por favor intenta de nuevo en unos segundos.';
        } else {
          friendlyMessage = `Error del servidor (${code}). Por favor intenta de nuevo.`;
        }
      } else if (
        errorMessage.toLowerCase().includes('failed to fetch') ||
        errorMessage.toLowerCase().includes('networkerror') ||
        errorMessage.toLowerCase().includes('load failed')
      ) {
        friendlyMessage = 'No se puede conectar con el servidor. Verifica tu conexión a internet.';
      }

      return {
        id:              this.generateMessageId(),
        type:            'error',
        content:         friendlyMessage,
        timestamp:       Date.now(),
        recommendations: [],
      };
    }
  }

  private generateSessionId(): string {
    // F-07 / Paso 3 (06/04/2026): Persistir session_id en localStorage con TTL 24h.
    // Sin esta persistencia, cada recarga de página genera un session_id nuevo
    // y el backend crea una sesión nueva vacía — rompiendo la memoria multi-turno.
    //
    // Flujo completo:
    //   1. Primera visita: se genera session_id nuevo + se guarda en localStorage
    //   2. Misma visita, mensaje 2: se envía el mismo session_id → backend acumula turns
    //   3. El backend retorna el session_id canónico en session_metadata.session_id
    //   4. syncSessionFromBackend() actualiza localStorage con el valor del servidor
    //   5. Próxima visita (< 24h): se recupera de localStorage → misma sesión
    //   6. Próxima visita (> 24h): TTL expirado → nueva sesión
    //
    // TTL 24h coincide con el TTL de Redis en el backend (86400s).
    try {
      const stored = localStorage.getItem('rr_widget_session_id');
      const storedTs = localStorage.getItem('rr_widget_session_ts');
      const TTL_MS = 24 * 60 * 60 * 1000; // 24 horas en ms

      if (stored && storedTs) {
        const age = Date.now() - parseInt(storedTs, 10);
        if (age < TTL_MS) {
          // Sesión válida — reusar
          return stored;
        }
        // TTL expirado — limpiar y generar nueva
        localStorage.removeItem('rr_widget_session_id');
        localStorage.removeItem('rr_widget_session_ts');
      }
    } catch {
      // localStorage no disponible (iframe, modo privado extremo) — continuar
    }

    // Generar nuevo session_id
    const newId = `widget_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    try {
      localStorage.setItem('rr_widget_session_id', newId);
      localStorage.setItem('rr_widget_session_ts', String(Date.now()));
    } catch {
      // No crítico — el session_id funcionará en memoria durante esta visita
    }
    return newId;
  }

  private syncSessionFromBackend(backendSessionId: string): void {
    // Actualizar el session_id con el valor canónico que devuelve el servidor.
    // El backend puede normalizar o transformar el session_id recibido
    // (ej. añadir prefijo de mercado). Este método garantiza que el widget
    // siempre use el mismo ID que el servidor tiene en Redis.
    if (!backendSessionId || backendSessionId === this.sessionId) return;

    this.sessionId = backendSessionId;
    try {
      localStorage.setItem('rr_widget_session_id', backendSessionId);
      localStorage.setItem('rr_widget_session_ts', String(Date.now()));
    } catch {
      // No crítico
    }
  }

  private generateUserId(): string {
    try {
      const existingId = localStorage.getItem('rr_widget_user_id');
      if (existingId) return existingId;

      const newId = `widget_user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('rr_widget_user_id', newId);
      return newId;
    } catch {
      return `widget_user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
  }

  private generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private detectPageType(): string {
    const path = window.location.pathname.toLowerCase();
    if (path.includes('/products/') || path.includes('/product/')) return 'product';
    if (path.includes('/collections/') || path.includes('/category/')) return 'category';
    if (path.includes('/cart')) return 'cart';
    if (path.includes('/checkout')) return 'checkout';
    if (path.includes('/search')) return 'search';
    return 'general';
  }

  private extractProductId(): string | undefined {
    const path = window.location.pathname;
    const productMatch = path.match(/\/products\/([^/]+)/);
    if (productMatch) return productMatch[1];

    const productMeta = document.querySelector('meta[property="product:retailer_item_id"]');
    if (productMeta) return productMeta.getAttribute('content') || undefined;

    const productElement = document.querySelector('[data-product-id]');
    if (productElement) return productElement.getAttribute('data-product-id') || undefined;

    return undefined;
  }

  updateConfig(newConfig: Partial<WidgetConfig>): void {
    this.config = { ...this.config, ...newConfig };
  }

  getSessionInfo() {
    return { sessionId: this.sessionId, userId: this.userId };
  }
}
