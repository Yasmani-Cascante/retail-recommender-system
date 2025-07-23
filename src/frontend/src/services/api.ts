import type { WidgetConfig, Message, ProductRecommendation } from '../types/widget';

interface ConversationRequest {
  query: string;
  user_id?: string;
  session_id?: string;
  market_id?: string;
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
          'X-Widget-Version': '1.0.0',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
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
      let friendlyMessage = 'Sorry, I encountered an error. Please try again.';
      
      if (errorMessage.includes('fetch')) {
        friendlyMessage = 'Unable to connect to the server. Please check your internet connection.';
      } else if (errorMessage.includes('401') || errorMessage.includes('403')) {
        friendlyMessage = 'Authentication error. Please contact support.';
      } else if (errorMessage.includes('500')) {
        friendlyMessage = 'Server error. Please try again in a moment.';
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