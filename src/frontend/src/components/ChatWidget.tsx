import { useState, useCallback, useEffect } from 'react';
import { X } from 'lucide-react';
import { clsx } from 'clsx';

import { ChatBubble } from './ChatBubble';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ConversationAPI } from '../services/api';
import type { WidgetConfig, Message, ConversationState } from '../types/widget';

interface ChatWidgetProps {
  config: WidgetConfig;
  className?: string;
}

export function ChatWidget({ config, className }: ChatWidgetProps) {
  const [state, setState] = useState<ConversationState>({
    sessionId: '',
    messages: [],
    isLoading: false,
    isMinimized: false,
  });
  
  const [isOpen, setIsOpen] = useState(false);
  const [api] = useState(() => new ConversationAPI(config));

  // Initialize with welcome message
  useEffect(() => {
    const welcomeMessage: Message = {
      id: 'welcome',
      type: 'assistant',
      content: '👋 Hi! I\'m here to help you find the perfect products. What are you looking for today?',
      timestamp: Date.now(),
      recommendations: [],
    };

    setState(prev => ({
      ...prev,
      messages: [welcomeMessage],
    }));
  }, []);

  const handleSendMessage = useCallback(async (messageText: string) => {
    // Add user message immediately
    const userMessage: Message = {
      id: `user_${Date.now()}`,
      type: 'user',
      content: messageText,
      timestamp: Date.now(),
    };

    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage],
      isLoading: true,
    }));

    try {
      // Send to API and get response
      const assistantMessage = await api.sendMessage(messageText);
      
      setState(prev => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
        isLoading: false,
        sessionId: assistantMessage.metadata?.sessionId || prev.sessionId,
      }));

    } catch (error) {
      console.error('Error sending message:', error);
      
      const errorMessage: Message = {
        id: `error_${Date.now()}`,
        type: 'error',
        content: 'Sorry, something went wrong. Please try again.',
        timestamp: Date.now(),
      };

      setState(prev => ({
        ...prev,
        messages: [...prev.messages, errorMessage],
        isLoading: false,
      }));
    }
  }, [api]);

  const handleToggle = useCallback(() => {
    setIsOpen(prev => !prev);
    setState(prev => ({ ...prev, isMinimized: false }));
  }, []);

  const handleMinimize = useCallback(() => {
    setState(prev => ({ ...prev, isMinimized: true }));
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    setState(prev => ({ ...prev, isMinimized: false }));
  }, []);

  return (
    <div className={clsx('rr-widget-container', className)}>
      {/* Chat Interface */}
      {isOpen && !state.isMinimized && (
        <div className="rr-fixed rr-bottom-20 rr-right-4 rr-w-80 rr-h-96 rr-bg-white rr-rounded-lg rr-shadow-xl rr-border rr-border-gray-200 rr-flex rr-flex-col rr-z-40 rr-animate-slide-up">
          {/* Header */}
          <div className="rr-bg-primary-600 rr-text-white rr-px-4 rr-py-3 rr-rounded-t-lg rr-flex rr-items-center rr-justify-between">
            <div>
              <h3 className="rr-font-semibold rr-text-sm">Product Assistant</h3>
              <p className="rr-text-xs rr-opacity-90">Ask me anything!</p>
            </div>
            
            <button
              onClick={handleClose}
              className="rr-text-white rr-hover:rr-bg-primary-700 rr-rounded rr-p-1 rr-transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <MessageList 
            messages={state.messages} 
            isLoading={state.isLoading} 
          />

          {/* Input */}
          <MessageInput
            onSendMessage={handleSendMessage}
            disabled={state.isLoading}
            placeholder="Ask about products, get recommendations..."
          />
        </div>
      )}

      {/* Chat Bubble */}
      <ChatBubble
        isOpen={isOpen}
        isMinimized={state.isMinimized}
        hasUnreadMessages={false}
        onToggle={handleToggle}
        onMinimize={handleMinimize}
      />
    </div>
  );
}