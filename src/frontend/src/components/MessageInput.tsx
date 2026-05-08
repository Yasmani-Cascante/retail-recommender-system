import React, { useState, useRef, useEffect } from 'react';
import styles from './MessageInput.module.css';

interface MessageInputProps {
  onSendMessage: (message: string) => void;
  /** Callback invocado cuando el usuario selecciona una imagen.
   *  El componente sólo valida tamaño (5 MB) y tipo; la lógica de
   *  búsqueda visual vive en ChatWidget.handleImageUpload. */
  onImageUpload?: (file: File) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Cuando false (default) el botón de cámara no se renderiza.
   *  ChatWidget lo activa cuando VISUAL_SEARCH_ENABLED está disponible. */
  visualSearchEnabled?: boolean;
}

export function MessageInput({
  onSendMessage,
  onImageUpload,
  disabled = false,
  placeholder = 'Escribe tu consulta...',
  visualSearchEnabled = false,
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Ref para el <input type="file"> oculto que activa el selector de imagen.
  // Se resetea en handleFileChange (e.target.value = '') para permitir
  // seleccionar la misma imagen dos veces consecutivas.
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  /**
   * handleFileChange — invocado cuando el usuario selecciona una imagen.
   *
   * Valida:
   *   - Que exista al menos un archivo seleccionado
   *   - Que el tipo sea imagen (el atributo accept ya filtra en el picker,
   *     pero validamos por si acaso el navegador lo omite)
   *   - Que el tamaño no supere 5 MB (límite del backend)
   *
   * Resetea e.target.value para que el mismo archivo pueda enviarse de
   * nuevo si el usuario lo necesita (sin el reset, onChange no dispara).
   */
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Siempre resetear para que onChange vuelva a disparar con el mismo archivo
    e.target.value = '';
    if (!file) return;

    // Validación de tipo (defensa doble ante navegadores que ignoran 'accept')
    if (!file.type.startsWith('image/')) {
      console.warn('[VisualSearch] Archivo rechazado: no es imagen', file.type);
      return;
    }

    // Validación de tamaño: 5 MB máximo (el backend rechaza con 413 si supera este límite)
    const MAX_BYTES = 5 * 1024 * 1024;
    if (file.size > MAX_BYTES) {
      console.warn(
        `[VisualSearch] Imagen demasiado grande: ${Math.round(file.size / 1024)}KB (máx 5MB)`,
      );
      return;
    }

    onImageUpload?.(file);
  };

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

        {/* Botón cámara — visible solo cuando visualSearchEnabled=true.
            El <input type="file"> está oculto; el botón lo activa con .click().
            El atributo 'capture' NO se usa deliberadamente: queremos que el
            usuario pueda elegir entre la cámara o la galería de fotos. */}
        {visualSearchEnabled && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              aria-hidden="true"
              tabIndex={-1}
            />
            <button
              type="button"
              className={`${styles.iconBtn} ${styles.cameraBtn}`}
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              title="Buscar por imagen"
              aria-label="Buscar productos por imagen"
            >
              {/* Cámara — SVG inline, sin dependencia de librería externa */}
              <svg
                width="16" height="16" viewBox="0 0 24 24"
                fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </button>
          </>
        )}

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
