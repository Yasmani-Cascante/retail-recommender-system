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
  metadata?: {
    sessionId?: string;
    intentAnalysis?: any;
    marketContext?: any;
  };
}

export interface ProductRecommendation {
  id: string;
  title: string;
  description: string;
  price: number;
  category: string;
  score: number;
  imageUrl?: string;
}

export interface ConversationState {
  sessionId: string;
  messages: Message[];
  isLoading: boolean;
  isMinimized: boolean;
  userId?: string;
}