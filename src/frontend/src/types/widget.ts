export interface WidgetConfig {
  apiUrl: string;
  apiKey: string;
  marketId?: string;
  theme?: 'light' | 'dark' | 'auto';
  position?: 'bottom-right' | 'bottom-left' | 'center';
  primaryColor?: string;
  language?: string;
  // F-04: ID del cliente Shopify logueado (inyectado desde theme.liquid
  // via data-customer-id="{{ customer.id }}"). Vacío para usuarios anónimos.
  customerId?: string;
  // Nombre del cliente para el saludo personalizado (opcional).
  // Se puede pasar via data-customer-name="{{ customer.first_name }}".
  customerName?: string;
}

export interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system' | 'error';
  content: string;
  timestamp: number;
  recommendations?: ProductRecommendation[];
  kb_document?: string;
  /**
   * suggestionChip — datos del chip de sugerencia que originó este mensaje.
   * Cuando el usuario hace click en un chip de sugerencia contextual o en
   * el botón "Ver similares", este campo guarda el texto del chip Y la imagen
   * del producto para que MessageList lo renderice visualmente como una
   * pastilla dentro de la burbuja del usuario, igual que hace Zalando.
   * Undefined para mensajes escritos manualmente por el usuario.
   */
  suggestionChip?: {
    /** Texto visible en la pastilla (ej. "Ver similares a VESTIDO CORTO EMMA") */
    label: string;
    /** URL de la imagen del producto para mostrar en la pastilla (opcional) */
    image_url?: string;
  };
  metadata?: {
    sessionId?: string;
    intentAnalysis?: unknown;
    marketContext?: unknown;
  };
}

export interface ProductRecommendation {
  id: string;
  title: string;
  description: string;
  price: number;
  // FIX (27/03/2026): currency was missing from the type — ProductCard received
  // undefined and defaulted to 'EUR' even for non-EUR markets. Now it flows from
  // the backend through normalizeRecommendation() → ProductCard.formatPrice().
  currency: string;
  category: string;
  // FIX (10/04/2026): vendor/marca — campo 'vendor' de Shopify.
  // Puede estar vacío si el producto no tiene marca asignada.
  vendor: string;
  score: number;
  image_url?: string;
  // FIX (27/03/2026): url field added so ProductCard can navigate to the product
  // page when the backend supplies it. The backend returns it inconsistently —
  // it is optional here and the card renders without it gracefully.
  url?: string;
}

/**
 * ActiveProductContext — producto seleccionado por el usuario como contexto
 * de la conversación actual (patrón "Let's chat about this item" de Zalando).
 *
 * Cuando el usuario hace click en el icono 💬 de una tarjeta de producto
 * recomendado, este objeto se guarda en el estado de ChatWidget y:
 *   1. Se muestra un chip de contexto encima del input con imagen + título.
 *   2. sendMessage() envía el handle del producto seleccionado como
 *      widget_context.product_id en lugar del producto de la página URL.
 *   3. El usuario puede quitar el chip (×) para volver al contexto de la URL.
 */
export interface ActiveProductContext {
  /** ID numérico del producto en Shopify (ej. "9978786152757") */
  id: string;
  /** Título del producto para mostrarlo en el chip */
  title: string;
  /** URL de la imagen para el chip (puede ser undefined) */
  image_url?: string;
  /**
   * Handle — slug de URL del producto (ej. "vestido-corto-emma-champagne").
   * Este es el valor que se envía como widget_context.product_id al backend.
   * Se deriva de product.url: "/products/{handle}" → extraemos el handle.
   * Si url no está disponible, usamos id como fallback.
   */
  handle: string;
}

export interface ConversationState {
  sessionId: string;
  messages: Message[];
  isLoading: boolean;
  isMinimized: boolean;
  userId?: string;
}

export interface RecapTurn {
  role: 'user' | 'assistant';
  content: string;
}

export type ServiceStatus = 'healthy' | 'warming' | 'down';
