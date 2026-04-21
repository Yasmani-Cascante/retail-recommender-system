import React, { useState, useRef, useEffect } from 'react';
import styles from './MessageInput.module.css';

interface MessageInputProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function MessageInput({
  onSendMessage,
  disabled = false,
  placeholder = 'Escribe tu consulta...',
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent | React.MouseEvent) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  // Auto-resize del textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 100)}px`;
    }
  }, [message]);

  const canSend = message.trim().length > 0 && !disabled;

  return (
    <div className={styles.inputArea}>
      <div className={styles.inputRow}>
        <textarea
          ref={textareaRef}
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className={styles.textarea}
          aria-label="Escribe un mensaje"
        />

        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSend}
          className={`${styles.sendBtn} ${
            canSend ? styles.sendBtnActive : styles.sendBtnDisabled
          }`}
          aria-label="Enviar mensaje"
        >
          {/* SVG inline — sin dependencia de lucide en runtime Shopify */}
          <svg
            width="16" height="16" viewBox="0 0 24 24"
            fill="none" stroke="currentColor"
            strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          >
            <path d="m22 2-7 20-4-9-9-4Z"/>
            <path d="M22 2 11 13"/>
          </svg>
        </button>
      </div>

      <p className={styles.footer}>AI-Shoppings · Asistente de moda</p>
    </div>
  );
}
