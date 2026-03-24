import { useEffect, useRef } from 'react';
import type { Message } from '../types/widget';
import { ProductCard } from './ProductCard';
import styles from './MessageList.module.css';

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
}

export function MessageList({ messages, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className={styles.list}>
      {messages.map((message) => (
        <div
          key={message.id}
          className={`${styles.row} ${
            message.type === 'user' ? styles.rowUser : styles.rowAssistant
          }`}
        >
          {/* Avatar del asistente (izquierda) */}
          {message.type !== 'user' && (
            <div className={styles.avatar} aria-hidden="true">✨</div>
          )}

          <div>
            {/* Burbuja principal */}
            <div
              className={`${styles.bubble} ${
                message.type === 'user'
                  ? styles.bubbleUser
                  : message.type === 'error'
                  ? styles.bubbleError
                  : styles.bubbleAssistant
              }`}
            >
              {message.content}
            </div>

            {/* Tarjetas de productos recomendados */}
            {message.recommendations && message.recommendations.length > 0 && (
              <div>
                <span className={styles.recoLabel}>Recomendado para ti</span>
                {message.recommendations.slice(0, 3).map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Indicador de escritura */}
      {isLoading && (
        <div className={styles.typing}>
          <div className={styles.avatar} aria-hidden="true">✨</div>
          <div className={styles.typingBubble} aria-label="El asistente está escribiendo">
            <span className={styles.typingDot} />
            <span className={styles.typingDot} />
            <span className={styles.typingDot} />
          </div>
        </div>
      )}

      <div ref={messagesEndRef} aria-hidden="true" />
    </div>
  );
}
