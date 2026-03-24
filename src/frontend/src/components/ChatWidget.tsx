import { useState, useCallback, useEffect } from 'react';
import { ChatBubble } from './ChatBubble';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ConversationAPI } from '../services/api';
import type { WidgetConfig, Message, ConversationState } from '../types/widget';
import styles from './ChatWidget.module.css';

interface ChatWidgetProps {
  config: WidgetConfig;
}

export function ChatWidget({ config }: ChatWidgetProps) {
  const [state, setState] = useState<ConversationState>({
    sessionId: '',
    messages: [],
    isLoading: false,
    isMinimized: false,
  });

  const [isOpen, setIsOpen] = useState(false);
  const [api] = useState(() => new ConversationAPI(config));

  // Mensaje de bienvenida
  useEffect(() => {
    const welcomeMessage: Message = {
      id: 'welcome',
      type: 'assistant',
      content: '👋 ¡Hola! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?',
      timestamp: Date.now(),
      recommendations: [],
    };
    setState(prev => ({ ...prev, messages: [welcomeMessage] }));
  }, []);

  const handleSendMessage = useCallback(async (messageText: string) => {
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
      const assistantMessage = await api.sendMessage(messageText);
      setState(prev => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
        isLoading: false,
        sessionId: assistantMessage.metadata?.sessionId || prev.sessionId,
      }));
    } catch {
      const errorMessage: Message = {
        id: `error_${Date.now()}`,
        type: 'error',
        content: 'Lo siento, ha ocurrido un error. Por favor intenta de nuevo.',
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

  const handleClose = useCallback(() => {
    setIsOpen(false);
    setState(prev => ({ ...prev, isMinimized: false }));
  }, []);

  return (
    <>
      {/* ── Panel de chat ─────────────────────────────── */}
      {isOpen && !state.isMinimized && (
        <div className={styles.panel} role="dialog" aria-label="Asistente de moda">
          
          {/* Header */}
          <div className={styles.header}>
            <div className={styles.headerLeft}>
              <div className={styles.headerAvatar} aria-hidden="true">✨</div>
              <div>
                <div className={styles.headerName}>Asistente de Moda</div>
                <div className={styles.headerStatus}>En línea</div>
              </div>
            </div>

            <button
              onClick={handleClose}
              className={styles.closeBtn}
              aria-label="Cerrar chat"
            >
              ✕
            </button>
          </div>

          {/* Mensajes */}
          <MessageList messages={state.messages} isLoading={state.isLoading} />

          {/* Input */}
          <MessageInput
            onSendMessage={handleSendMessage}
            disabled={state.isLoading}
            placeholder="Escribe tu consulta..."
          />
        </div>
      )}

      {/* ── Burbuja flotante ─────────────────────────── */}
      <ChatBubble
        isOpen={isOpen}
        isMinimized={state.isMinimized}
        hasUnreadMessages={false}
        onToggle={handleToggle}
        onMinimize={() => {}}
      />
    </>
  );
}
