export interface WidgetConfig {
  apiUrl: string;
  apiKey: string;
  marketId?: string;
  theme?: 'light' | 'dark' | 'auto';
  position?: 'bottom-right' | 'bottom-left' | 'center';
  primaryColor?: string;
  language?: string;
}

export interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system' | 'error';
  content: string;
  timestamp: number;
  recommendations?: ProductRecommendation[];
  kb_document?: string;
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
  score: number;
  image_url?: string;
  // FIX (27/03/2026): url field added so ProductCard can navigate to the product
  // page when the backend supplies it. The backend returns it inconsistently —
  // it is optional here and the card renders without it gracefully.
  url?: string;
}

export interface ConversationState {
  sessionId: string;
  messages: Message[];
  isLoading: boolean;
  isMinimized: boolean;
  userId?: string;
}
