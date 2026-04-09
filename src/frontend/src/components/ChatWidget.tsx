import { useState, useCallback, useEffect } from 'react';
import { ChatBubble } from './ChatBubble';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ConversationAPI } from '../services/api';
import type { WidgetConfig, Message, ConversationState, ActiveProductContext, ProductRecommendation } from '../types/widget';
import styles from './ChatWidget.module.css';

interface ChatWidgetProps {
  config: WidgetConfig;
}

// Sugerencias iniciales inspiradas en el estilo Zalando.
// Se muestran solo en la pantalla de bienvenida (sin mensajes del usuario aún).
const SUGGESTION_CHIPS = [
  'Muéstrame las tendencias de esta semana',
  'Busco un look para una ocasión especial',
  'Recomiéndame algo informal para el fin de semana',
  'Ayúdame a elegir mi talla',
];

/**
 * buildProductSuggestions — genera chips de sugerencia contextuales
 * al producto seleccionado, igual que Zalando.
 *
 * Las sugerencias varían según la categoría del producto para ser
 * más relevantes. Si no hay categoría reconocible, se usan sugerencias genéricas.
 */
function buildProductSuggestions(product: ActiveProductContext): string[] {
  const title = product.title.toLowerCase();

  // Detectar categoría desde el título para sugerencias contextuales
  if (title.includes('vestido') || title.includes('dress')) {
    return [
      `¿Qué accesorios combinan con este vestido?`,
      `¿Tenéis este vestido en otros colores?`,
      `¿Qué zapatos recomiendas para este look?`,
      `Muéstrame vestidos similares`,
    ];
  }
  if (title.includes('camisa') || title.includes('shirt') || title.includes('blusa') || title.includes('top')) {
    return [
      `¿Con qué pantalón combina esta prenda?`,
      `¿Está disponible en otras tallas?`,
      `Muéstrame opciones similares`,
      `¿Qué accesorios le quedan bien?`,
    ];
  }
  if (title.includes('zapato') || title.includes('bota') || title.includes('shoe') || title.includes('boot')) {
    return [
      `¿Con qué outfits quedan bien?`,
      `¿Qué talla me recomiendas?`,
      `Muéstrame zapatos similares`,
    ];
  }
  if (title.includes('aro') || title.includes('collar') || title.includes('pulsera') || title.includes('accesorio')) {
    return [
      `¿Con qué ropa combina mejor?`,
      `¿Tenéis otros accesorios similares?`,
      `Muéstrame el conjunto completo`,
    ];
  }
  // Sugerencias genéricas si no se reconoce la categoría
  return [
    `Cuéntame más sobre este producto`,
    `¿Está disponible en otras opciones?`,
    `Muéstrame productos similares`,
    `¿Qué combina bien con esto?`,
  ];
}

/**
 * extractHandleFromUrl — extrae el handle de producto de una URL de Shopify.
 *
 * Dado que product.url tiene el formato "/products/{handle}" o
 * "https://shop.myshopify.com/products/{handle}", extrae el handle
 * para usarlo como widget_context.product_id en el backend.
 *
 * Si la URL no tiene el formato esperado, devuelve el id numérico como fallback.
 */
function extractHandleFromUrl(url: string | undefined, fallbackId: string): string {
  if (!url) return fallbackId;
  const match = url.match(/\/products\/([^/?#]+)/);
  return match ? match[1] : fallbackId;
}

export function ChatWidget({ config }: ChatWidgetProps) {
  const [state, setState] = useState<ConversationState>({
    sessionId: '',
    messages: [],
    isLoading: false,
    isMinimized: false,
  });

  // isOpen: el panel flotante está visible
  const [isOpen, setIsOpen] = useState(false);
  // isExpanded: modo pantalla completa (inspirado en Zalando)
  const [isExpanded, setIsExpanded] = useState(false);

  /**
   * activeProductContext — producto seleccionado por el usuario para contextualizar
   * la conversación (patrón "Let's chat about this item" de Zalando).
   *
   * null  → contexto normal (usa el producto de la URL actual o ninguno)
   * value → muestra el chip de contexto encima del input + sugerencias contextuales;
   *         los mensajes enviados usarán este handle como product_id
   */
  const [activeProductContext, setActiveProductContext] = useState<ActiveProductContext | null>(null);

  const [api] = useState(() => new ConversationAPI(config));

  // Determinar si hay conversación activa (el usuario ya envió al menos un mensaje)
  const hasUserMessages = state.messages.some(m => m.type === 'user');

  // ── Saludo personalizado ────────────────────────────────────────────────
  // Si hay nombre de cliente lo usamos. Si no, saludo genérico.
  // Solo se muestra cuando el chat está abierto y no hay mensajes de usuario.
  const greetingName = config.customerName?.trim() || '';
  const isLoggedIn = Boolean(config.customerId);

  // ── Mensaje de bienvenida en el historial ──────────────────────────────
  useEffect(() => {
    const welcomeText = greetingName
      ? `¡Hola, ${greetingName}! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?`
      : '👋 ¡Hola! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?';

    const welcomeMessage: Message = {
      id: 'welcome',
      type: 'assistant',
      content: welcomeText,
      timestamp: Date.now(),
      recommendations: [],
    };
    setState(prev => ({ ...prev, messages: [welcomeMessage] }));
  }, [greetingName]);

  /**
   * handleSendMessage — envía un mensaje al backend.
   *
   * Acepta `chip` (texto visual para la burbuja) y `productHandle` (override
   * explícito del handle del producto). Cuando viene de "Ver similares", el
   * handle se pasa directamente para evitar la race condition de useState:
   * React no garantiza que setActiveProductContext sea visible en el mismo
   * tick, por lo que activeProductContext?.handle puede ser null si se
   * llama inmediatamente después de setActiveProductContext.
   */
  const handleSendMessage = useCallback(async (
    messageText: string,
    chip?: { label: string; image_url?: string },
    explicitProductHandle?: string,
  ) => {
    const productHandle = explicitProductHandle ?? activeProductContext?.handle ?? undefined;

    const userMessage: Message = {
      id: `user_${Date.now()}`,
      type: 'user',
      content: messageText,
      timestamp: Date.now(),
      // Guardar el chip que originó este mensaje (si viene de uno)
      suggestionChip: chip,
    };

    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage],
      isLoading: true,
    }));

    // Limpiar el contexto activo al enviar — el backend ya lo tiene
    // y los próximos turnos partirán desde las nuevas recomendaciones
    setActiveProductContext(null);

    try {
      // Pasar productHandle a api.sendMessage() — si es undefined,
      // api.ts usará extractProductId() de la URL (comportamiento por defecto)
      const assistantMessage = await api.sendMessage(messageText, productHandle);
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
  }, [api, activeProductContext]);

  /**
   * handleSuggestion — chip de sugerencia clickado.
   *
   * Dos casos:
   *
   * A) Sugerencias de bienvenida (sin activeProductContext):
   *    El usuario selecciona "Muéstrame tendencias", etc.
   *    → Sin chip visual. Solo se muestra el mensaje con el texto.
   *
   * B) Sugerencias contextuales de "Preguntar" (con activeProductContext):
   *    El usuario selecciona "¿Qué accesorios combinan?" etc.
   *    → Chip visual con imagen + TÍTULO DEL PRODUCTO (no el texto de la query).
   *    → Mensaje con el texto de la query (visible en la burbuja).
   *
   * La separación chip/mensaje es deliberada:
   *   chip.label  = identifica el PRODUCTO de referencia
   *   content     = la PREGUNTA del usuario sobre ese producto
   * Son siempre distintos, por lo que la burbuja siempre muestra el mensaje.
   */
  const handleSuggestion = useCallback((text: string) => {
    const chip = activeProductContext
      ? { label: activeProductContext.title, image_url: activeProductContext.image_url }
      : undefined;
    handleSendMessage(text, chip);
  }, [handleSendMessage, activeProductContext]);

  /**
   * handleChatAbout — activado cuando el usuario hace click en el botón 💬
   * de una tarjeta de producto recomendado.
   *
   * Construye el ActiveProductContext extrayendo el handle de product.url
   * y lo guarda en estado. Esto:
   *   1. Muestra el chip de contexto encima del input
   *   2. Muestra sugerencias contextuales al producto
   *   3. Hace scroll suave al input para que el usuario vea el chip
   */
  const handleChatAbout = useCallback((product: ProductRecommendation) => {
    const handle = extractHandleFromUrl(product.url, product.id);
    setActiveProductContext({
      id: product.id,
      title: product.title,
      image_url: product.image_url,
      handle,
    });
    // Scroll suave al fondo para que el chip sea visible
    setTimeout(() => {
      document.querySelector('[data-chat-input]')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 50);
  }, []);

  /**
   * handleShowSimilar — "Show me similar items" (Sabor 2).
   * Envía automáticamente un mensaje de recomendaciones similares.
   *
   * FIX (race condition): NO usa setActiveProductContext + setTimeout.
   * En su lugar pasa el handle directamente como tercer parámetro de
   * handleSendMessage para que sea leído en el mismo tick sin depender
   * de que React haya aplicado el cambio de estado.
   *
   * FIX (intent detection): La query anterior "Muéstrame productos similares
   * a este" era clasificada como INFORMATIONAL (0.74) por el ML, lo que
   * activaba el KB en lugar de las recomendaciones. La nueva query incluye
   * la palabra "recomendar" que el detector transaccional reconoce mejor.
   */
  const handleShowSimilar = useCallback((product: ProductRecommendation) => {
    const handle = extractHandleFromUrl(product.url, product.id);
    // const chipText = `Ver similares a ${product.title}`;
    const chipText = `${product.title}`;
    
    // Query con vocabulario transaccional para que el intent detector lo clasifique
    // correctamente como TRANSACTIONAL y no derive al Knowledge Base
    const queryText = `Recoméndame productos similares a este`;


    // Pasar handle directamente (tercer arg) — evita la race condition de useState.
    // El chip lleva label + image_url para renderizar la imagen en la burbuja.
    handleSendMessage(queryText, { label: chipText, image_url: product.image_url }, handle);
  }, [handleSendMessage]);

  /**
   * handleClearContext — el usuario hace click en × del chip de contexto.
   * Vuelve al contexto normal (producto de la URL o ninguno).
   */
  const handleClearContext = useCallback(() => {
    setActiveProductContext(null);
  }, []);

  const handleToggle = useCallback(() => {
    setIsOpen(prev => !prev);
    setState(prev => ({ ...prev, isMinimized: false }));
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    setIsExpanded(false);
    setState(prev => ({ ...prev, isMinimized: false }));
  }, []);

  const handleToggleExpand = useCallback(() => {
    setIsExpanded(prev => !prev);
  }, []);

  // Sugerencias para el producto activo (solo cuando hay chip activo)
  const productSuggestions = activeProductContext
    ? buildProductSuggestions(activeProductContext)
    : null;

  return (
    <>
      {/* ── Panel de chat ───────────────────────────────────────────── */}
      {isOpen && !state.isMinimized && (
        <div
          className={`${styles.panel} ${isExpanded ? styles.panelExpanded : ''}`}
          role="dialog"
          aria-label="Asistente de moda"
          aria-modal="true"
        >
          {/* Fondo decorativo sutil */}
          <div className={styles.float_form_wrapper} />

          {/* ── Header ──────────────────────────────────────────────── */}
          <div className={styles.header}>
            <div className={styles.headerLeft}>
              <div className={styles.headerAvatar} aria-hidden="true">
                {/* Icono del asistente — mismo SVG que el ChatBubble */}
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                  width="22" height="22" fill="none" color="white">
                  <g clipPath="url(#clip0_990_39490)">
                    <path d="M13.4733 5H21V18.2102L16.14 22V18.2102H6V12.2941"
                      stroke="currentColor" strokeWidth="2.03704"
                      strokeMiterlimit="10" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M10 5.00002C7.74328 5.00002 6.00049 3.25689 6.00049 1C6.00049 3.25689 4.25672 5.00021 2 5.00021C4.25672 5.00021 5.9997 6.74311 5.9997 9C5.9997 6.74311 7.74328 5.00002 10 5.00002Z"
                      stroke="currentColor" strokeWidth="2.03704" strokeLinejoin="round" />
                  </g>
                </svg>
              </div>
              <div>
                <div className={styles.headerName}>Asistente de Moda</div>
                <div className={styles.headerStatus}>En línea</div>
              </div>
            </div>

            <div className={styles.headerActions}>
              {/* Botón Maximizar / Restaurar — solo en desktop */}
              <button
                onClick={handleToggleExpand}
                className={styles.expandBtn}
                aria-label={isExpanded ? 'Restaurar tamaño' : 'Maximizar chat'}
                title={isExpanded ? 'Restaurar' : 'Maximizar'}
              >
                {isExpanded ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="4 14 10 14 10 20" />
                    <polyline points="20 10 14 10 14 4" />
                    <line x1="10" y1="14" x2="3" y2="21" />
                    <line x1="21" y1="3" x2="14" y2="10" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 3 21 3 21 9" />
                    <polyline points="9 21 3 21 3 15" />
                    <line x1="21" y1="3" x2="14" y2="10" />
                    <line x1="3" y1="21" x2="10" y2="14" />
                  </svg>
                )}
              </button>

              {/* Botón Cerrar */}
              <button onClick={handleClose} className={styles.closeBtn}
                aria-label="Cerrar chat">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          {/* ── Pantalla de bienvenida (estilo Zalando) ──────────────
              Se muestra solo cuando no hay mensajes de usuario todavía.
              Incluye el saludo con nombre si el usuario está logueado.   */}
          {!hasUserMessages && (
            <div className={styles.welcomeScreen}>
              {isLoggedIn && greetingName && (
                <div className={styles.personalGreeting}>
                  <span className={styles.personalGreetingHi}>Hola, {greetingName} 👋</span>
                  <span className={styles.personalGreetingVerif}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"
                      viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                      aria-hidden="true">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                      <polyline points="9 12 11 14 15 10" />
                    </svg>
                    Cuenta verificada
                  </span>
                </div>
              )}
              <h2 className={styles.welcomeTitle}>
                {isLoggedIn && greetingName
                  ? `¿Qué buscas hoy, ${greetingName}?`
                  : '¿En qué puedo ayudarte?'}
              </h2>
              <p className={styles.welcomeSubtitle}>
                Pregúntame sobre moda, tallas, tendencias o te ayudo a encontrar tu próximo look.
              </p>
              <div className={styles.suggestions} aria-label="Sugerencias">
                <span className={styles.suggestionsLabel}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    aria-hidden="true">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                  </svg>
                  Sugerencias
                </span>
                {SUGGESTION_CHIPS.map((chip) => (
                  <button key={chip} className={styles.chip} onClick={() => handleSuggestion(chip)}>
                    {chip}
                  </button>
                ))}
              </div>
              <p className={styles.betaNote}>
                Estoy en beta, sigo aprendiendo.{' '}
                <a href="#" className={styles.betaLink} onClick={(e) => { e.preventDefault(); }}>
                  Más información
                </a>
              </p>
            </div>
          )}

          {/* ── Lista de mensajes — visible cuando hay conversación ── */}
          {hasUserMessages && (
            <MessageList
              messages={state.messages}
              isLoading={state.isLoading}
              onChatAbout={handleChatAbout}
              onShowSimilar={handleShowSimilar}
            />
          )}

          {/* ── Zona inferior: chip de contexto + sugerencias + input ── */}
          <div className={styles.bottomZone} data-chat-input>

            {/* ── Chip de contexto activo — patrón "Let's chat about this item" ──
                Se muestra cuando el usuario ha seleccionado un producto con 💬.
                Incluye imagen en miniatura, título truncado y botón × para cancelar. */}
            {activeProductContext && (
              <div className={styles.contextChip} role="status" aria-live="polite">
                {/* Miniatura del producto */}
                {activeProductContext.image_url ? (
                  <img
                    src={activeProductContext.image_url}
                    alt=""
                    className={styles.contextChipImg}
                    aria-hidden="true"
                  />
                ) : (
                  <span className={styles.contextChipEmoji} aria-hidden="true">🛍️</span>
                )}

                {/* Info del producto */}
                <div className={styles.contextChipInfo}>
                  <span className={styles.contextChipLabel}>Hablemos sobre</span>
                  <span className={styles.contextChipTitle}>{activeProductContext.title}</span>
                </div>

                {/* Botón × para limpiar el contexto */}
                <button
                  className={styles.contextChipClose}
                  onClick={handleClearContext}
                  aria-label="Quitar producto del contexto"
                  title="Volver al contexto general"
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="2.5"
                    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            )}

            {/* ── Suggestion chips contextuales al producto activo ──
                Se muestran debajo del chip y desaparecen al enviar el mensaje.
                El usuario puede usarlos o escribir su propio mensaje. */}
            {productSuggestions && (
              <div className={styles.productSuggestions} aria-label="Sugerencias para este producto">
                <span className={styles.productSuggestionsLabel}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    aria-hidden="true">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                  </svg>
                  Sugerencias
                </span>
                <div className={styles.productSuggestionsRow}>
                  {productSuggestions.map((chip) => (
                    <button
                      key={chip}
                      className={styles.productSuggestionChip}
                      onClick={() => handleSuggestion(chip)}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── Input de texto ── */}
            <MessageInput
              onSendMessage={handleSendMessage}
              disabled={state.isLoading}
              placeholder={
                activeProductContext
                  ? `Pregunta sobre ${activeProductContext.title}...`
                  : 'Escribe tu mensaje...'
              }
            />
          </div>
        </div>
      )}

      {/* ── Burbuja flotante ────────────────────────────────────────── */}
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
