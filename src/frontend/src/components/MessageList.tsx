import { useEffect, useRef, useState } from 'react';
import type { Message } from '../types/widget';
import { ProductCard } from './ProductCard';
import styles from './MessageList.module.css';

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
}

export function MessageList({ messages, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [expandedKbId, setExpandedKbId] = useState<string | null>(null);

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
            <div className={styles.avatar} aria-hidden="true">
              <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  width="24"
                  height="24"
                  fill="none"
                >
                  <g clipPath="url(#clip0_990_39490)">
                    <path
                      d="M13.4733 5H21V18.2102L16.14 22V18.2102H6V12.2941"
                      stroke="currentColor"
                      strokeWidth="2.03704"
                      strokeMiterlimit="10"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M10 5.00002C7.74328 5.00002 6.00049 3.25689 6.00049 1C6.00049 3.25689 4.25672 5.00021 2 5.00021C4.25672 5.00021 5.9997 6.74311 5.9997 9C5.9997 6.74311 7.74328 5.00002 10 5.00002Z"
                      stroke="currentColor"
                      strokeWidth="2.03704"
                      strokeLinejoin="round"
                      style={{ transitionProperty: 'transform', transitionDuration: '0.3s', transform: 'scale(1.0)' }}
                    />
                  </g>
                </svg>
            </div>
          )}

          <div className={styles.messageContent}>
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

            {/* Botón para ver el documento KB completo */}
            {message.kb_document && (
              <button
                className={styles.kbToggleBtn}
                onClick={() =>
                  setExpandedKbId(expandedKbId === message.id ? null : message.id)
                }
                aria-expanded={expandedKbId === message.id}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                  <polyline points="10 9 9 9 8 9"/>
                </svg>
                {expandedKbId === message.id ? 'Ocultar documento' : 'Ver política completa'}
              </button>
            )}

            {/* Panel expandible con el documento KB */}
            {message.kb_document && expandedKbId === message.id && (
              <div className={styles.kbPanel} role="region" aria-label="Documento completo">
                <div className={styles.kbPanelHeader}>
                  <span>Documento completo</span>
                  <button
                    className={styles.kbCloseBtn}
                    onClick={() => setExpandedKbId(null)}
                    aria-label="Cerrar documento"
                  >
                    ✕
                  </button>
                </div>
                <div className={styles.kbPanelBody}>
                  {message.kb_document}
                </div>
              </div>
            )}

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
          <div className={styles.avatar} aria-hidden="true">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="none"
              color='white'
            >
              <g clipPath="url(#clip0_990_39490)">
                <path
                  d="M13.4733 5H21V18.2102L16.14 22V18.2102H6V12.2941"
                  stroke="currentColor"
                  strokeWidth="2.03704"
                  strokeMiterlimit="10"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M10 5.00002C7.74328 5.00002 6.00049 3.25689 6.00049 1C6.00049 3.25689 4.25672 5.00021 2 5.00021C4.25672 5.00021 5.9997 6.74311 5.9997 9C5.9997 6.74311 7.74328 5.00002 10 5.00002Z"
                  stroke="currentColor"
                  strokeWidth="2.03704"
                  strokeLinejoin="round"
                  style={{ transitionProperty: 'transform', transitionDuration: '0.3s', transform: 'scale(1.0)' }}
                />
              </g>
            </svg>
          </div>
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
