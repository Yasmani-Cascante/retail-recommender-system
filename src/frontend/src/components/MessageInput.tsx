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
  onOutfitSearch,
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
  // S1 FASE 4: Ref para el <input type="file"> del outfit search.
  // Separado del fileInputRef de visual search para no mezclar los callbacks.
  const outfitFileInputRef = useRef<HTMLInputElement>(null);

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

  /**
   * handleOutfitFileChange — S1 FASE 4: Valida y reenvía el archivo al callback de outfit search.
   * Reutiliza las mismas validaciones que handleFileChange (tipo + tamaño).
   */
  const handleOutfitFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) return;
    const MAX_BYTES = 5 * 1024 * 1024;
    if (file.size > MAX_BYTES) return;
    onOutfitSearch?.(file);
  };

  return (
    <div className={styles.inputArea}>
      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>    
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
        {/* Botón cámara — visible solo cuando visualSearchEnabled=true.
            El <input type="file"> está oculto; el botón lo activa con .click().
            El atributo 'capture' NO se usa deliberadamente: queremos que el
            usuario pueda elegir entre la cámara o la galería de fotos. */}
        {visualSearchEnabled && (
          <div className={styles.iconGroup}>
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
                width="18" height="18" viewBox="0 0 24 24"
                fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </button>

            {/* S1 FASE 4: Botón completar outfit — solo cuando el callback está registrado.
                El mismo flujo que el botón de cámara: abre selector de archivo,
                pero llama onOutfitSearch en lugar de onImageUpload.
                El emoji 👗 es semánticamente correcto y no requiere librería. */}
            {onOutfitSearch && (
              <>
                <input
                  ref={outfitFileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  style={{ display: 'none' }}
                  onChange={handleOutfitFileChange}
                  aria-hidden="true"
                  tabIndex={-1}
                />
                <button
                  type="button"
                  className={`${styles.iconBtn} ${styles.outfitBtn}`}
                  onClick={() => outfitFileInputRef.current?.click()}
                  disabled={disabled}
                  title="Completar outfit"
                  aria-label="Buscar prendas para completar el outfit"
                >
                  {/* Icono hanger / percha — más descriptivo que solo el emoji */}
                  {/* <svg
                    width="16" height="16" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M20.38 19H3.62a1 1 0 0 1-.76-1.64L12 8" />
                    <path d="M12 8V5" />
                    <circle cx="12" cy="4" r="1" />
                    <path d="m12 8-8.24 9.36" />
                  </svg> */}
                  <svg height="18" width="18" viewBox="0 0 512 512"  fill="currentColor"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <style type="text/css"> </style> <g> <path d="M506.663,405.366c-3.461-6.338-8.574-11.877-15.002-15.908L261.733,245.175v-20.395 c-0.004-0.702,0.333-1.336,0.836-1.784c2.056-0.18,4.778-0.508,7.98-1.135c6.559-1.299,15.178-3.688,23.833-9.272 c12.695-8.256,23.217-19.498,30.597-32.787c7.375-13.288,11.586-28.652,11.582-44.859c0.008-25.501-10.392-48.756-27.106-65.456 c-16.693-16.714-39.947-27.099-65.44-27.099c-19.108,0-37.013,5.83-51.765,15.812c-14.759,9.98-26.464,24.075-33.508,40.708 c-3.811,9.011,0.411,19.41,9.421,23.224c9.014,3.808,19.417-0.403,23.225-9.413c4.322-10.228,11.59-18.984,20.712-25.144 c9.13-6.158,20.026-9.742,31.914-9.742c15.815,0,29.984,6.36,40.376,16.73c10.362,10.384,16.718,24.553,16.722,40.38 c-0.004,10.093-2.58,19.447-7.126,27.651c-4.547,8.19-11.079,15.178-18.917,20.269c-3.054,2.038-7.6,3.531-11.274,4.217 c-1.828,0.351-3.415,0.538-4.449,0.62c-0.522,0.052-0.9,0.075-1.097,0.082h-0.105l-2.404,0.03l-2.359,0.702 c-16.065,4.756-27.091,19.507-27.095,36.267v20.94L18.578,390.622l0.004-0.014C6.716,398.886-0.011,412.301,0,426.217 c0,4.344,0.658,8.742,2.001,13.004c5.684,18.096,22.444,30.391,41.399,30.391h425.197c19.35,0,36.352-12.803,41.708-31.399v-0.008 c1.132-3.964,1.695-8.003,1.695-11.989C512,418.863,510.13,411.711,506.663,405.366z M476.242,428.426v-0.008 c-0.978,3.397-4.102,5.756-7.644,5.756H43.4c-3.475,0-6.548-2.27-7.585-5.569c-0.258-0.806-0.369-1.605-0.369-2.389 c0.007-2.553,1.224-5.017,3.4-6.525h0.008L244.53,276.224l228.292,143.251c1.206,0.762,2.102,1.747,2.748,2.912 c0.642,1.164,0.989,2.486,0.989,3.83C476.559,426.941,476.454,427.665,476.242,428.426z"></path> </g> </g></svg>
                  {/* <span style={{ fontSize: '13px', lineHeight: 1 }}>👗</span> */}
                </button>
              </>
            )}
          </div>
        )}

      </div>

       

      <p className={styles.footer}>AI-Shoppings · Asistente de moda</p>
    </div>
  );
}
