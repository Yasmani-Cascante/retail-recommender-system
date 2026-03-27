import type { WidgetConfig, Message, ProductRecommendation } from '../types/widget';

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
  };
}

interface ConversationResponse {
  answer: string;
  recommendations: ProductRecommendation[];
  kb_document?: string;
  session_metadata: {
    session_id: string;
    user_id: string;
  };
  intent_analysis?: any;
  market_context?: any;
  personalization_metadata?: any;
  metadata?: any;
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

  async sendMessage(message: string): Promise<Message> {
    try {
      const request: ConversationRequest = {
        query: message,
        user_id: this.userId,
        session_id: this.sessionId,
        market_id: this.config.marketId || 'US',
        language: navigator.language.split('-')[0],  // ✅ AGREGAR soporte de idioma
        widget_context: {
          page_url: window.location.href,
          page_type: this.detectPageType(),
          product_id: this.extractProductId(),
          user_agent: navigator.userAgent,
        }
      };

      const response = await fetch(`${this.config.apiUrl}/v1/mcp/conversation`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.config.apiKey,
          'Accept-Language': navigator.language || 'en-US',  // ✅ AGREGAR soporte de idioma
          'X-Widget-Version': '1.0.0',
        },
        body: JSON.stringify(request),
      });

      // FIX (23/03/2026): Lanzar errores diferenciados por código HTTP.
      // Antes: throw new Error('API Error: 500 ...') → caía al catch → se
      // confundía con error de red porque el mensaje podía contener 'fetch'.
      // Ahora: errores HTTP se manejan explícitamente ANTES del catch genérico.
      if (!response.ok) {
        // Intentar leer el body del error para más contexto
        let errorDetail = '';
        try {
          const errBody = await response.json();
          errorDetail = errBody.detail || errBody.message || '';
        } catch {
          // Body no es JSON, continuar sin detalle
        }
        // Lanzar con un marcador que NO contenga 'fetch' para no confundir el catch
        throw new Error(`HTTP_${response.status}:${errorDetail}`);
      }

      const data: ConversationResponse = await response.json();

      // Update session info
      if (data.session_metadata?.session_id) {
        this.sessionId = data.session_metadata.session_id;
      }

      return {
        id: this.generateMessageId(),
        type: 'assistant',
        content: data.answer,
        timestamp: Date.now(),
        recommendations: data.recommendations || [],
        kb_document: data.kb_document,
        metadata: {
          sessionId: this.sessionId,
          intentAnalysis: data.intent_analysis,
          marketContext: data.market_context,
        }
      };

    } catch (error) {
      console.error('Widget API Error:', error);
      
      // Return a user-friendly error message
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      let friendlyMessage = 'Lo siento, ha ocurrido un error. Por favor intenta de nuevo.';

      // FIX (23/03/2026): Diferenciar errores HTTP (HTTP_NNN:) de errores de red.
      // Los errores HTTP usan el prefijo HTTP_NNN: — no contienen 'fetch'.
      // Los errores de red (TypeError: Failed to fetch) sí contienen 'fetch'.
      if (errorMessage.startsWith('HTTP_')) {
        const code = errorMessage.split(':')[0].replace('HTTP_', '');
        if (code === '401' || code === '403') {
          friendlyMessage = 'Error de autenticación. Por favor contacta con soporte.';
        } else if (code === '429') {
          friendlyMessage = 'Demasiadas solicitudes. Por favor espera un momento.';
        } else if (code.startsWith('5')) {
          // Errores 5xx del servidor — mensaje claro, no confundirlo con red
          friendlyMessage = 'El servidor encontró un error. Por favor intenta de nuevo en unos segundos.';
        } else {
          friendlyMessage = `Error del servidor (${code}). Por favor intenta de nuevo.`;
        }
      } else if (
        errorMessage.toLowerCase().includes('failed to fetch') ||
        errorMessage.toLowerCase().includes('networkerror') ||
        errorMessage.toLowerCase().includes('load failed')
      ) {
        // Error genuino de red — sin conexión al servidor
        friendlyMessage = 'No se puede conectar con el servidor. Verifica tu conexión a internet.';
      }
      
      return {
        id: this.generateMessageId(),
        type: 'error',
        content: friendlyMessage,
        timestamp: Date.now(),
        recommendations: [],
      };
    }
  }

  private generateSessionId(): string {
    return `widget_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateUserId(): string {
    // Check if user has existing ID in localStorage
    try {
      const existingId = localStorage.getItem('rr_widget_user_id');
      if (existingId) return existingId;

      const newId = `widget_user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('rr_widget_user_id', newId);
      return newId;
    } catch (error) {
      // Fallback if localStorage is not available
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
    // Try to extract product ID from URL or page data
    const path = window.location.pathname;
    const productMatch = path.match(/\/products\/([^\/]+)/);
    
    if (productMatch) {
      return productMatch[1];
    }

    // Try to find product ID in meta tags or data attributes
    const productMeta = document.querySelector('meta[property="product:retailer_item_id"]');
    if (productMeta) {
      return productMeta.getAttribute('content') || undefined;
    }

    // Try to find in data attributes
    const productElement = document.querySelector('[data-product-id]');
    if (productElement) {
      return productElement.getAttribute('data-product-id') || undefined;
    }

    return undefined;
  }

  // Public method to update configuration
  updateConfig(newConfig: Partial<WidgetConfig>) {
    this.config = { ...this.config, ...newConfig };
  }

  // Public method to get current session info
  getSessionInfo() {
    return {
      sessionId: this.sessionId,
      userId: this.userId,
    };
  }
}