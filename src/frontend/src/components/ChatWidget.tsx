import { useState, useCallback, useEffect, useRef } from 'react';
import { ChatBubble } from './ChatBubble';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ConversationAPI } from '../services/api';
import type { WidgetConfig, Message, ConversationState, ActiveProductContext, ProductRecommendation, RecapTurn, ServiceStatus, OutfitResult } from '../types/widget';
import styles from './ChatWidget.module.css';
import stylesmessage from './MessageList.module.css';

import { AiBubble } from './AiBubble';

interface ChatWidgetProps {
  config: WidgetConfig;
}

// Sugerencias iniciales que se muestran en la pantalla de bienvenida.
// Indexadas por código de idioma ISO 639-1 (2 letras).
// Cada chip está verificado contra el intent detector:
//   ES: TRANSACTIONAL (mostrar +0.5), INFORMATIONAL policy_payment, etc.
//   EN: TRANSACTIONAL (show +0.5), INFORMATIONAL, etc.
// Se lee a través de getSuggestionChips(lang) más abajo.
const SUGGESTION_CHIPS_BY_LANG: Record<string, string[]> = {
  es: [
    'Muéstrame los productos nuevos',
    // 'Muéstrame los productos más populares',
    'Recomiéndame un vestido para una boda',
    '¿Cuáles son sus métodos de pago?',
    '¿Cómo funciona las devoluciónes?',
  ],
  en: [
    'Show me the new arrivals',
    'Show me the most popular products',
    'What payment methods do you accept?',
    'I\'m looking for a wedding dress',
    'How does the return policy work?',
  ],
  de: [
    'Zeig mir die neuen Produkte',
    'Welche Zahlungsmethoden akzeptieren Sie?',
    'Ich suche ein Kleid für eine Hochzeit',
    'Wie funktioniert die Rückgabe?',
  ],
  fr: [
    'Montrez-moi les nouveautés',
    'Quels modes de paiement acceptez-vous?',
    'Je cherche une robe pour un mariage',
    'Comment fonctionne le retour?',
  ],
};

/** Devuelve los chips de sugerencia para un código de idioma.
 *  Normaliza 'en-US' → 'en', etc. Fallback a español si no hay traducción. */
function getSuggestionChips(lang: string): string[] {
  const code = lang.split('-')[0].toLowerCase();
  return SUGGESTION_CHIPS_BY_LANG[code] ?? SUGGESTION_CHIPS_BY_LANG['es'];
}

/**
 * buildProductSuggestions — genera chips de sugerencia contextuales
 * al producto seleccionado, igual que Zalando.
 *
 * FIX (20/04/2026): Añadido parámetro `lang` para soporte bilingüe.
 * Antes los chips estaban hardcodeados en español, ignorando el idioma
 * del navegador. Ahora se seleccionan chips ES o EN según `uiLang`.
 */
function buildProductSuggestions(product: ActiveProductContext, lang: string): string[] {
  const title = product.title.toLowerCase();
  const isEN = lang.split('-')[0].toLowerCase() === 'en';

  if (title.includes('vestido') || title.includes('dress')) {
    return isEN ? [
      `Show me similar dresses`,
      `Is it available in other sizes?`,
      `What accessories go with this dress?`,
      `I want something for a wedding`,
    ] : [
      `Muéstrame vestidos similares a este`,
      `¿Está disponible en otras tallas?`,
      `¿Qué accesorios combinan con este vestido?`,
      `Quiero algo para una boda`,
    ];
  }
  if (title.includes('camisa') || title.includes('shirt') || title.includes('blusa') || title.includes('top')) {
    return isEN ? [
      `Show me similar tops`,
      `Is it available in other sizes?`,
      `What bottoms go with this?`,
      `What material is this?`,
    ] : [
      `Busco opciones similares a esta prenda`,
      `¿Está disponible en otras tallas?`,
      `¿Con qué pantalón combina esta prenda?`,
      `¿Qué materiales usa esta prenda?`,
    ];
  }
  if (title.includes('zapato') || title.includes('bota') || title.includes('shoe') || title.includes('boot')) {
    return isEN ? [
      `Show me similar shoes`,
      `How do I find my shoe size?`,
      `What outfits go with these?`,
    ] : [
      `Muéstrame zapatos similares`,
      `¿Cómo sé mi talla de zapato?`,
      `¿Con qué outfits quedan bien?`,
    ];
  }
  if (title.includes('aro') || title.includes('collar') || title.includes('pulsera') || title.includes('accesorio')) {
    return isEN ? [
      `Show me similar accessories`,
      `What outfits go best with this?`,
      `I'm looking for a complete outfit`,
    ] : [
      `Muéstrame accesorios similares`,
      `¿Con qué ropa combina mejor?`,
      `Busco un conjunto completo`,
    ];
  }
  // Generic fallback
  return isEN ? [
    `Is this item in stock?`,
    `What sizes do you have?`,
    `Show me similar products`,
    `Show me something that goes with this`,
  ] : [
    `Tienen este artículo en stock?`,
    `¿Qué tallas tienen?`,
    `Muéstrame productos similares`,
    `Busco algo que combine con esto`,
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

function isProductPage(pathname: string): boolean {
  const lower = pathname.toLowerCase();
  return lower.includes('/products/') || lower.includes('/product/');
}

function getProductHandleFromPath(pathname: string): string | undefined {
  const match = pathname.match(/\/products\/([^/?#]+)/);
  return match ? match[1] : undefined;
}

function getProductPageTitle(): string | undefined {
  // 1. Try Open Graph meta tags (most reliable)
  const ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute('content')
    || document.querySelector('meta[name="twitter:title"]')?.getAttribute('content');
  if (ogTitle?.trim()) return ogTitle.trim();

  // 2. Try JSON-LD structured data
  try {
    const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of Array.from(jsonLdScripts)) {
      const data = JSON.parse(script.textContent || '');
      if (data['@type'] === 'Product' && data.name) {
        return String(data.name).trim();
      }
    }
  } catch {
    // Ignore JSON parsing errors
  }

  // 3. Try common Shopify product title selectors
  const titleSelectors = [
    '.product-title',
    '.product__title',
    '.product-single__title',
    '.product-title h1',
    '.product__title h1',
    'h1.product-title',
    'h1.product__title',
    'h1',
    '[data-product-title]'
  ];

  for (const selector of titleSelectors) {
    const element = document.querySelector(selector);
    if (element?.textContent?.trim()) {
      return element.textContent.trim();
    }
  }

  // 4. Try document.title as fallback
  const title = document.title?.trim();
  if (!title) return undefined;

  const separators = [' | ', ' - ', ' — '];
  for (const separator of separators) {
    if (title.includes(separator)) {
      return title.split(separator)[0].trim();
    }
  }
  return title;
}

function getProductPageImageUrl(): string | undefined {
  // 1. Try Open Graph meta tags
  const ogImage = document.querySelector('meta[property="og:image"]')?.getAttribute('content')
    || document.querySelector('meta[name="twitter:image"]')?.getAttribute('content');
  if (ogImage?.trim()) return ogImage.trim();

  // 2. Try JSON-LD structured data
  try {
    const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of Array.from(jsonLdScripts)) {
      const data = JSON.parse(script.textContent || '');
      if (data['@type'] === 'Product' && data.image) {
        if (Array.isArray(data.image)) {
          return String(data.image[0]).trim();
        }
        return String(data.image).trim();
      }
    }
  } catch {
    // Ignore JSON parsing errors
  }

  // 3. Try common Shopify product image selectors
  const imageSelectors = [
    '.product-image img',
    '.product__image img',
    '.product-gallery img',
    '.product-photos img',
    '.product-single__photo img',
    '[data-product-image] img',
    '.product-image',
    '.product__image'
  ];

  for (const selector of imageSelectors) {
    const img = document.querySelector(selector) as HTMLImageElement;
    if (img?.src?.trim()) {
      return img.src.trim();
    }
  }

  // 4. Try window.product global (some Shopify themes expose this)
  try {
    if ((window as any).product?.featured_image?.src) {
      return (window as any).product.featured_image.src;
    }
    if ((window as any).product?.images?.[0]?.src) {
      return (window as any).product.images[0].src;
    }
  } catch {
    // Ignore global access errors
  }

  return undefined;
}

function buildProductContextFromPage(): ActiveProductContext | null {
  if (!isProductPage(window.location.pathname)) return null;
  const handle = getProductHandleFromPath(window.location.pathname);
  if (!handle) return null;

  return {
    id: handle,
    title: getProductPageTitle() ?? 'este producto',
    image_url: getProductPageImageUrl(),
    handle,
  };
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
  // En móvil siempre iniciamos expandido para pantalla completa
  const [isExpanded, setIsExpanded] = useState(() => window.innerWidth <= 480);

  // Detectar cambios de tamaño de pantalla para ajustar isExpanded en móvil
  useEffect(() => {
    const handleResize = () => {
      const isMobile = window.innerWidth <= 480;
      // Si es móvil y el chat está abierto, forzar modo expandido
      if (isMobile && isOpen) {
        setIsExpanded(true);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isOpen]);

  /**
   * activeProductContext — producto seleccionado por el usuario para contextualizar
   * la conversación (patrón "Let's chat about this item" de Zalando).
   *
   * null  → contexto normal (usa el producto de la URL actual o ninguno)
   * value → muestra el chip de contexto encima del input + sugerencias contextuales;
   *         los mensajes enviados usarán este handle como product_id
   */
  const [activeProductContext, setActiveProductContext] = useState<ActiveProductContext | null>(null);
  const [autoProductContextFilled, setAutoProductContextFilled] = useState(false);

  /**
   * pageProductContext — producto de la página actual (URL).
   *
   * Se extrae una sola vez al abrir el chat y NO se limpia al enviar mensajes.
   * Sirve para mostrar siempre en el placeholder que los mensajes están
   * vinculados al producto que el usuario está viendo.
   *
   * A diferencia de activeProductContext, este es persistente durante toda
   * la sesión del chat y proporciona contexto implícito al usuario.
   */
  const [pageProductContext, setPageProductContext] = useState<ActiveProductContext | null>(null);

  // Header scroll behavior — hide/show on scroll (solo cuando no está expandido)
  const [isHeaderHidden, setIsHeaderHidden] = useState(false);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const lastScrollY = useRef(0);

  const [api] = useState(() => new ConversationAPI(config));

  // visualSearchAvailable — refleja el flag VISUAL_SEARCH_ENABLED del backend.
  // Se establece en el health check al abrir el chat. Empieza en false para que
  // el botón de cámara NO se muestre hasta que el backend confirme que está activo.
  // Esto evita que el usuario vea el botón y reciba un error 503 al usarlo.
  const [visualSearchAvailable, setVisualSearchAvailable] = useState(false);

  // isVisualSearching — true mientras se espera la respuesta del embedding-service.
  const [isVisualSearching, setIsVisualSearching] = useState(false);
  // S1 FASE 4: isOutfitSearching — true mientras se espera la respuesta del outfit search.
  // Separado de isVisualSearching para que los dos botones sean independientes.
  const [isOutfitSearching, setIsOutfitSearching] = useState(false);

  // ── Cold Start UX state ─────────────────────────────────────────────────
  // serviceStatus: tracks whether the backend is healthy, warming up, or down
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>('healthy');
  // showWarmingOverlay: true when health check takes >1.5s (Case 1)
  const [showWarmingOverlay, setShowWarmingOverlay] = useState(false);
  // isResuming: true when session resume is in progress (used in Task 8)
  const [isResuming, setIsResuming] = useState(false);
  // sessionRecap: previous session turns for recap display (used in Task 9)
  const [sessionRecap, setSessionRecap] = useState<RecapTurn[] | null>(null);
  // showInactivityWarning: true when user has been idle (used in Task 7)
  const [showInactivityWarning, setShowInactivityWarning] = useState(false);
  // lastInteractionRef: tracks last user interaction timestamp.
  // Intentionally initialized to 0 so it's always reset on first chat open.
  const lastInteractionRef = useRef<number>(0);
  // Ref mirror of showInactivityWarning so the timer callback reads it without
  // needing it in the deps array (prevents restarting the interval on state change).
  const showInactivityWarningRef = useRef(false);
  // sessionRecap and setSessionRecap are consumed by the resuming UI (Task 9).

  // Determinar si hay conversación activa (el usuario ya envió al menos un mensaje)
  const hasUserMessages = state.messages.some(m => m.type === 'user');

  // ── Idioma del navegador — fuente de verdad para el UI chrome ──────────────
  // Usamos navigator.language (ej. 'en', 'en-US', 'de', 'fr') para determinar
  // el idioma de los mensajes predefinidos, bienvenida y chips de sugerencia.
  // Esta es la misma fuente que api.ts usa para el header Accept-Language,
  // garantizando consistencia entre la UI y las peticiones al backend.
  // Se normaliza con split('-')[0] para manejar variantes regionales (en-US → en).
  const uiLang = (navigator.language || 'es').split('-')[0].toLowerCase();

  // ── Saludo personalizado ────────────────────────────────────────────────
  // Si hay nombre de cliente lo usamos. Si no, saludo genérico.
  // Solo se muestra cuando el chat está abierto y no hay mensajes de usuario.
  const greetingName = config.customerName?.trim() || '';
  const isLoggedIn = Boolean(config.customerId);

  // ── Textos de UI localizados según el idioma del navegador ────────────────
  // Todas las cadenas de texto visibles del UI chrome se definen aquí,
  // indexadas por uiLang. Fallback implícito a español si el idioma no tiene
  // traducción (gracias a ?? en getSuggestionChips y a los defaults inline).
  const UI_TEXT: Record<string, Record<string, string>> = {
    es: {
      welcome:          greetingName ? `¡Hola, ${greetingName}! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?` : '👋 ¡Hola! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?',
      welcomeTitle:     isLoggedIn && greetingName ? `¿Qué buscas hoy, ${greetingName}?` : '¿En qué puedo ayudarte?',
      welcomeSubtitle:  'Pregúntame sobre moda, tallas, tendencias o te ayudo a encontrar tu próximo look.',
      suggestions:      'Sugerencias',
      betaNote:         'Estoy en beta, sigo aprendiendo.',
      betaLink:         'Más información',
      chatAbout:        'Hablemos sobre',
      // Solución A: Siempre mostrar el producto de la URL en el placeholder
      // para que el usuario sepa que sus mensajes están vinculados al producto actual
      inputPlaceholder: pageProductContext ? `Pregunta sobre ${pageProductContext.title}...` : 'Escribe tu mensaje...',
      error:            'Lo siento, ha ocurrido un error. Por favor intenta de nuevo.',
      verifiedAccount:  'Cuenta verificada',
    },
    en: {
      welcome:          greetingName ? `Hello, ${greetingName}! I'm your personal fashion assistant. What are you looking for today?` : '👋 Hello! I\'m your personal fashion assistant. What are you looking for today?',
      welcomeTitle:     isLoggedIn && greetingName ? `What are you looking for today, ${greetingName}?` : 'How can I help you?',
      welcomeSubtitle:  'Ask me about fashion, sizes, trends, or let me help you find your next look.',
      suggestions:      'Suggestions',
      betaNote:         'I\'m in beta, still learning.',
      betaLink:         'More information',
      chatAbout:        'Let\'s chat about',
      // Solución A: Always show the current page product in the placeholder
      inputPlaceholder: pageProductContext ? `Ask about ${pageProductContext.title}...` : 'Type your message...',
      error:            'Sorry, an error occurred. Please try again.',
      verifiedAccount:  'Verified account',
    },
    de: {
      welcome:          greetingName ? `Hallo, ${greetingName}! Ich bin Ihr persönlicher Modeassistent. Was suchen Sie heute?` : '👋 Hallo! Ich bin Ihr persönlicher Modeassistent. Was suchen Sie heute?',
      welcomeTitle:     isLoggedIn && greetingName ? `Was suchen Sie heute, ${greetingName}?` : 'Wie kann ich Ihnen helfen?',
      welcomeSubtitle:  'Fragen Sie mich nach Mode, Größen, Trends oder ich helfe Ihnen, Ihren nächsten Look zu finden.',
      suggestions:      'Vorschläge',
      betaNote:         'Ich bin in der Beta-Phase, noch am Lernen.',
      betaLink:         'Mehr Informationen',
      chatAbout:        'Über dieses Produkt sprechen',
      // Lösung A: Immer das aktuelle Seitenprodukt im Placeholder anzeigen
      inputPlaceholder: pageProductContext ? `Frage über ${pageProductContext.title}...` : 'Nachricht eingeben...',
      error:            'Entschuldigung, ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.',
      verifiedAccount:  'Verifiziertes Konto',
    },
    fr: {
      welcome:          greetingName ? `Bonjour, ${greetingName} ! Je suis votre assistant mode personnel. Que cherchez-vous aujourd'hui ?` : '👋 Bonjour ! Je suis votre assistant mode personnel. Que cherchez-vous aujourd\'hui ?',
      welcomeTitle:     isLoggedIn && greetingName ? `Que cherchez-vous aujourd'hui, ${greetingName} ?` : 'Comment puis-je vous aider ?',
      welcomeSubtitle:  'Posez-moi des questions sur la mode, les tailles, les tendances ou aidez-moi à trouver votre prochain look.',
      suggestions:      'Suggestions',
      betaNote:         'Je suis en bêta, j\'apprends encore.',
      betaLink:         'Plus d\'informations',
      chatAbout:        'Parlons de',
      // Solution A: Toujours afficher le produit de la page actuelle dans le placeholder
      inputPlaceholder: pageProductContext ? `Question sur ${pageProductContext.title}...` : 'Écrivez votre message...',
      error:            'Désolé, une erreur s\'est produite. Veuillez réessayer.',
      verifiedAccount:  'Compte vérifié',
    },
  };

  // Helper: obtiene un texto de UI con fallback a español.
  const t = (key: string): string =>
    (UI_TEXT[uiLang]?.[key] ?? UI_TEXT['es'][key]) || '';

  // ── Mensaje de bienvenida en el historial ──────────────────────────────
  useEffect(() => {
    // El welcomeText ya es calculado por t() pero useEffect no tiene acceso
    // al valor reactivo actualizado de uiLang. Recalculamos localmente para
    // que el mensaje inicial se genere con el idioma correcto en el mount.
    const langCode = (navigator.language || 'es').split('-')[0].toLowerCase();
    const welcomeText = greetingName
      ? (langCode === 'en'
          ? `Hello, ${greetingName}! I'm your personal fashion assistant. What are you looking for today?`
          : langCode === 'de'
          ? `Hallo, ${greetingName}! Ich bin Ihr persönlicher Modeassistent. Was suchen Sie heute?`
          : langCode === 'fr'
          ? `Bonjour, ${greetingName} ! Je suis votre assistant mode personnel. Que cherchez-vous aujourd'hui ?`
          : `¡Hola, ${greetingName}! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?`)
      : (langCode === 'en'
          ? "👋 Hello! I'm your personal fashion assistant. What are you looking for today?"
          : langCode === 'de'
          ? '👋 Hallo! Ich bin Ihr persönlicher Modeassistent. Was suchen Sie heute?'
          : langCode === 'fr'
          ? "👋 Bonjour ! Je suis votre assistant mode personnel. Que cherchez-vous aujourd'hui ?"
          : '👋 ¡Hola! Soy tu asistente de moda personal. ¿Qué estás buscando hoy?');

    const welcomeMessage: Message = {
      id: 'welcome',
      type: 'assistant',
      content: welcomeText,
      timestamp: Date.now(),
      recommendations: [],
    };
    setState(prev => ({ ...prev, messages: [welcomeMessage] }));
  }, [greetingName]);

  useEffect(() => {
    if (!isOpen || activeProductContext || autoProductContextFilled) return;
    const pageContext = buildProductContextFromPage();
    if (!pageContext) return;

    setActiveProductContext(pageContext);
    setAutoProductContextFilled(true);
  }, [isOpen, activeProductContext, autoProductContextFilled]);

  // Inicializar pageProductContext cuando se abre el chat (solo una vez)
  useEffect(() => {
    if (!isOpen || pageProductContext) return;
    const pageContext = buildProductContextFromPage();
    if (pageContext) {
      setPageProductContext(pageContext);
    }
  }, [isOpen, pageProductContext]);

  // Header scroll behavior — hide/show on scroll (solo cuando no está expandido)
  useEffect(() => {
    if (!isOpen || isExpanded) {
      setIsHeaderHidden(false);
      return;
    }

    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const currentScrollY = container.scrollTop;
      const scrollDelta = currentScrollY - lastScrollY.current;

      // Solo ocultar header si hay scroll suficiente (evitar flickering)
      if (Math.abs(scrollDelta) < 5) return;

      // Scroll hacia abajo → ocultar header
      if (scrollDelta > 0 && !isHeaderHidden) {
        setIsHeaderHidden(true);
      }
      // Scroll hacia arriba → mostrar header
      else if (scrollDelta < 0 && isHeaderHidden) {
        setIsHeaderHidden(false);
      }

      lastScrollY.current = currentScrollY;
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [isOpen, isExpanded, isHeaderHidden]);

  // Reset header visibility cuando se expande/colapsa
  useEffect(() => {
    if (isExpanded) {
      setIsHeaderHidden(false);
    }
  }, [isExpanded]);

  // Keep showInactivityWarningRef in sync so the timer callback reads current value
  useEffect(() => { showInactivityWarningRef.current = showInactivityWarning; }, [showInactivityWarning]);

  // Case 1: Health check when chat opens — triggers Cloud Run warm-up
  useEffect(() => {
    if (!isOpen) return;
    // Reset inactivity clock on every open so the warning can't fire immediately
    lastInteractionRef.current = Date.now();

    let cancelled = false;
    const warmingTimer = setTimeout(() => {
      if (!cancelled) setShowWarmingOverlay(true);
    }, 1500);

    api.checkHealth().then((result) => {
      clearTimeout(warmingTimer);
      if (!cancelled) {
        setShowWarmingOverlay(false);
        if (result.status === 'healthy' || result.status === 'unknown') {
          setServiceStatus('healthy');
        }
        // Leer el flag de visual search desde el health check.
        // Si el backend no tiene el campo (monolito sin parche), default a false.
        // No se hace una petición separada — reutiliza el health check existente.
        setVisualSearchAvailable(result.visual_search_enabled ?? false);
      }
    });

    return () => {
      cancelled = true;
      clearTimeout(warmingTimer);
    };
  }, [isOpen]);

  // Case 2b post-"Let's continue": poll until healthy then re-enable
  useEffect(() => {
    if (!isResuming) return;

    const intervalId = setInterval(async () => {
      const result = await api.checkHealth();
      if (result.status === 'healthy') {
        setIsResuming(false);
        setServiceStatus('healthy');
        clearInterval(intervalId);
      }
    }, 5_000);

    return () => clearInterval(intervalId);
  }, [isResuming]);

  // Event-driven health check: fires once when the user returns to this tab.
  // Covers "service scaled to zero while user was away" without background polling.
  useEffect(() => {
    if (!isOpen || !hasUserMessages || serviceStatus !== 'healthy') return;

    const checkIfDown = async () => {
      const result = await api.checkHealth();
      if (result.status !== 'healthy') {
        setServiceStatus('down');
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') checkIfDown();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [isOpen, hasUserMessages, serviceStatus, api]);

  // Case 3: Silent close if service goes down on welcome screen
  useEffect(() => {
    if (serviceStatus === 'down' && !hasUserMessages) {
      setIsOpen(false);
    }
  }, [serviceStatus, hasUserMessages]);

  // Case 2a: 15-minute inactivity warning.
  // Deps are stable (no showInactivityWarning) — the ref mirror prevents restarting
  // the interval every time the warning state changes, which caused premature fires.
  useEffect(() => {
    if (!isOpen || !hasUserMessages) return;

    const checkInactivity = () => {
      const elapsed = Date.now() - lastInteractionRef.current;
      if (elapsed >= 15 * 60 * 1000 && !showInactivityWarningRef.current) {
        setShowInactivityWarning(true);
      }
    };

    const timerId = setInterval(checkInactivity, 60_000);
    return () => clearInterval(timerId);
  }, [isOpen, hasUserMessages]); // stable — showInactivityWarning read via ref

  // Auto-dismiss after 5 min AND run a proactive health check.
  // This is the only proactive detection path for idle users: Cloud Run's default
  // idle timeout is ~15 min, so by minute 20 the service is likely scaled to zero.
  useEffect(() => {
    if (!showInactivityWarning) return;
    const timer = setTimeout(async () => {
      const health = await api.checkHealth();
      if (health.status !== 'healthy') {
        setServiceStatus('down');
      } else {
        // Service is still up — reset the 15-min window so the warning doesn't
        // immediately re-show on the next interval tick.
        lastInteractionRef.current = Date.now();
      }
      setShowInactivityWarning(false);
    }, 5 * 60 * 1000);
    return () => clearTimeout(timer);
  }, [showInactivityWarning, api]);

  /**
   * handleSendMessage — envía un mensaje al backend.
   *
   * Acepta:
   *   - `chip`: chip visual explícito (sugerencias contextuales de producto)
   *   - `productHandle`: override explícito del handle del producto
   *   - `shouldAutoGenerateChip`: si true y no hay chip explícito, auto-genera desde activeProductContext
   *
   * Casos de uso:
   *   - Sugerencias de bienvenida: handleSendMessage(text) → sin chip
   *   - Sugerencias contextuales: handleSendMessage(text, chip) → con chip explícito
   *   - Mensajes manuales: handleSendMessage(text, undefined, undefined, true) → auto-genera si hay contexto
   */
  const handleSendMessage = useCallback(async (
    messageText: string,
    chip?: { label: string; image_url?: string },
    explicitProductHandle?: string,
    shouldAutoGenerateChip: boolean = false,
  ) => {
    lastInteractionRef.current = Date.now();
    setShowInactivityWarning(false);

    const productHandle = explicitProductHandle ?? activeProductContext?.handle ?? undefined;

    // Auto-generar chip solo si se solicita explícitamente y no hay uno provisto
    const finalChip = chip || (shouldAutoGenerateChip && activeProductContext
      ? { label: activeProductContext.title, image_url: activeProductContext.image_url }
      : undefined);

    const userMessage: Message = {
      id: `user_${Date.now()}`,
      type: 'user',
      content: messageText,
      timestamp: Date.now(),
      // Guardar el chip que originó este mensaje (si viene de uno)
      suggestionChip: finalChip,
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
      // Backend piggybacks shutdown_at on every conversation response.
      // When SIGTERM fires during the grace period the next response carries it,
      // so the user sees Case 2b after their last *successful* message.
      if (assistantMessage.metadata?.shutdownAt != null) {
        setServiceStatus('down');
      }
    } catch {
      // Check if the service went down (Cloud Run scaled to zero between messages).
      // This is the reactive substitute for background polling.
      const health = await api.checkHealth();
      if (health.status !== 'healthy') {
        setServiceStatus('down');
        setState(prev => ({ ...prev, isLoading: false }));
        return;
      }

      const errorMessage: Message = {
        id: `error_${Date.now()}`,
        type: 'error',
        // t() no está disponible en el callback (closure creado antes del render),
        // por lo que usamos navigator.language directamente como en useEffect.
        content: (() => {
          const lc = (navigator.language || 'es').split('-')[0].toLowerCase();
          if (lc === 'en') return 'Sorry, an error occurred. Please try again.';
          if (lc === 'de') return 'Entschuldigung, ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.';
          if (lc === 'fr') return "Désolé, une erreur s'est produite. Veuillez réessayer.";
          return 'Lo siento, ha ocurrido un error. Por favor intenta de nuevo.';
        })(),
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
   * A) Sugerencias de bienvenida (isWelcomeSuggestion = true):
   *    El usuario selecciona "Muéstrame tendencias", etc.
   *    → Sin chip visual. Solo se muestra el mensaje con el texto.
   *
   * B) Sugerencias contextuales de "Preguntar" (isWelcomeSuggestion = false):
   *    El usuario selecciona "¿Qué accesorios combinan?" etc.
   *    → Chip visual con imagen + TÍTULO DEL PRODUCTO (no el texto de la query).
   *    → Mensaje con el texto de la query (visible en la burbuja).
   *
   * La separación chip/mensaje es deliberada:
   *   chip.label  = identifica el PRODUCTO de referencia
   *   content     = la PREGUNTA del usuario sobre ese producto
   * Son siempre distintos, por lo que la burbuja siempre muestra el mensaje.
   */
  const handleSuggestion = useCallback((text: string, isWelcomeSuggestion: boolean = false) => {
    // Si es sugerencia de bienvenida, NO generar chip
    // Si es sugerencia contextual y hay activeProductContext, generar chip
    const chip = !isWelcomeSuggestion && activeProductContext
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

  /**
   * handleLetsContinue — Case 2b: resume session after service came back.
   * Fetches the session recap, marks resuming in progress, and optimistically
   * sets service to healthy (will be corrected by the next health-poll tick).
   */
  const handleLetsContinue = async () => {
    const recap = await api.getSessionRecap();
    setSessionRecap(recap.turns.length > 0 ? recap.turns : null);
    setIsResuming(true);
    setServiceStatus('healthy'); // optimistic — will be corrected by polling
  };

  /**
   * handleStartNewChat — Case 2b: discard current session and start fresh.
   */
  const handleStartNewChat = () => {
    api.resetSession();
    setState(prev => ({ ...prev, messages: prev.messages.slice(0, 1), sessionId: '' }));
    setServiceStatus('healthy');
    setShowInactivityWarning(false);
  };

  /**
   * handleCloseConversation — Case 2b: close the chat panel.
   */
  const handleCloseConversation = () => {
    setIsOpen(false);
  };

  /**
   * handleImageUpload — búsqueda visual de productos por imagen.
   *
   * Flujo completo:
   *   1. Crear URL de preview (blob:) para mostrar la imagen en la burbuja
   *      del usuario antes de recibir respuesta del backend.
   *   2. Añadir mensaje de usuario con suggestionChip que contiene la preview.
   *   3. Llamar api.searchByImage() — POST /v1/mcp/visual-search (multipart).
   *   4. Añadir mensaje de asistente con las recomendaciones (o sin resultados).
   *   5. Liberar la blob URL en finally para evitar memory leaks.
   *
   * Guardias:
   *   - Si isVisualSearching o state.isLoading ya es true, retornar inmediatamente
   *     para evitar peticiones en paralelo.
   *   - El mensaje de error cubre tanto el 503 (flag off, índice no construido)
   *     como errores de red, usando el mismo patrón de localizón que handleSendMessage.
   */
  const handleImageUpload = useCallback(async (file: File) => {
    // Guardia: no lanzar si ya hay una petición en vuelo
    if (isVisualSearching || state.isLoading) return;

    setIsVisualSearching(true);

    // URL temporal de preview — se libera en finally
    const previewUrl = URL.createObjectURL(file);

    // Mensaje del usuario: burbuja vacía con chip que muestra la imagen
    const lc = (navigator.language || 'es').split('-')[0].toLowerCase();
    const chipLabel = lc === 'en' ? 'Search by image' : 'Buscar por imagen';

    const userMsg: Message = {
      id: `vs_user_${Date.now()}`,
      type: 'user',
      content: '',        // Sin texto — el chip ya muestra la imagen
      timestamp: Date.now(),
      suggestionChip: {
        label: chipLabel,
        image_url: previewUrl,
      },
    };

    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMsg],
      isLoading: true,
    }));

    try {
      const recommendations = await api.searchByImage(
        file,
        config.marketId,
        8,
      );

      const hasResults = recommendations.length > 0;
      const replyText = hasResults
        ? (lc === 'en'
            ? `Found ${recommendations.length} visually similar products:`
            : `Encontré ${recommendations.length} producto${recommendations.length !== 1 ? 's' : ''} similares:`)
        : (lc === 'en'
            ? 'No similar products found. Try with another image.'
            : 'No encontré productos similares. Intenta con otra imagen.');

      const assistantMsg: Message = {
        id: `vs_assistant_${Date.now()}`,
        type: 'assistant',
        content: replyText,
        timestamp: Date.now(),
        recommendations: hasResults ? recommendations : undefined,
      };

      setState(prev => ({
        ...prev,
        messages: [...prev.messages, assistantMsg],
        isLoading: false,
      }));

    } catch (error) {
      // Extraer mensaje descriptivo del error (puede venir del backend: 503, 413, etc.)
      const rawMsg = error instanceof Error ? error.message : '';
      const friendlyMsg = rawMsg ||
        (lc === 'en'
          ? 'Visual search is not available right now. Please try again.'
          : 'La búsqueda visual no está disponible ahora. Inténtalo de nuevo.');

      const errorMsg: Message = {
        id: `vs_error_${Date.now()}`,
        type: 'error',
        content: friendlyMsg,
        timestamp: Date.now(),
      };

      setState(prev => ({
        ...prev,
        messages: [...prev.messages, errorMsg],
        isLoading: false,
      }));

    } finally {
      // Liberar la blob URL independientemente del resultado
      URL.revokeObjectURL(previewUrl);
      setIsVisualSearching(false);
    }
  }, [api, config.marketId, isVisualSearching, state.isLoading]);

  /**
   * handleOutfitSearch — S1 FASE 4: búsqueda de outfit completo por imagen.
   *
   * Flujo idéntico a handleImageUpload pero llama searchOutfitByImage() y
   * guarda el resultado en message.outfitResult (no en recommendations).
   * El renderizado categorizado lo hace MessageList cuando detecta outfitResult.
   */
  const handleOutfitSearch = useCallback(async (file: File) => {
    if (isOutfitSearching || state.isLoading) return;
    setIsOutfitSearching(true);

    const previewUrl = URL.createObjectURL(file);
    const lc = (navigator.language || 'es').split('-')[0].toLowerCase();
    const chipLabel = lc === 'en' ? 'Complete the outfit' : 'Completar outfit';

    // Mensaje del usuario: burbuja con chip que muestra la imagen de referencia
    const userMsg: Message = {
      id: `outfit_user_${Date.now()}`,
      type: 'user',
      content: '',
      timestamp: Date.now(),
      suggestionChip: { label: chipLabel, image_url: previewUrl },
    };

    setState(prev => ({ ...prev, messages: [...prev.messages, userMsg], isLoading: true }));

    try {
      const result: OutfitResult = await api.searchOutfitByImage(
        file,
        config.marketId,
        2,   // top_k_per_category
        0.7, // alpha
      );

      const categoriesFound = Object.keys(result.outfit ?? {});
      const totalProducts   = categoriesFound.reduce(
        (acc, cat) => acc + (result.outfit[cat]?.length ?? 0), 0
      );

      const hasResults = totalProducts > 0;
      const replyText  = hasResults
        ? (lc === 'en'
            ? `Here are suggestions to complete your outfit (${categoriesFound.length} categories):`
            : `Aquí tienes sugerencias para completar tu outfit (${categoriesFound.length} categorías):`)
        : (lc === 'en'
            ? 'No suggestions found for this outfit. Try with another photo.'
            : 'No encontré sugerencias para este outfit. Prueba con otra foto.');

      const assistantMsg: Message = {
        id: `outfit_assistant_${Date.now()}`,
        type: 'assistant',
        content: replyText,
        timestamp: Date.now(),
        // outfitResult lleva el mapa categorizado completo para que
        // MessageList lo renderice como un panel de outfits
        outfitResult: hasResults ? result : undefined,
      };

      setState(prev => ({
        ...prev,
        messages: [...prev.messages, assistantMsg],
        isLoading: false,
      }));

    } catch (error) {
      const raw = error instanceof Error ? error.message : '';
      const friendly = raw || (
        lc === 'en'
          ? 'Outfit search is not available right now. Please try again.'
          : 'La búsqueda de outfit no está disponible ahora. Inténtalo de nuevo.'
      );
      const errorMsg: Message = {
        id: `outfit_error_${Date.now()}`,
        type: 'error',
        content: friendly,
        timestamp: Date.now(),
      };
      setState(prev => ({ ...prev, messages: [...prev.messages, errorMsg], isLoading: false }));

    } finally {
      URL.revokeObjectURL(previewUrl);
      setIsOutfitSearching(false);
    }
  }, [api, config.marketId, isOutfitSearching, state.isLoading]);

  const handleToggle = useCallback(() => {
    const willOpen = !isOpen;
    setIsOpen(willOpen);
    // En móvil, al abrir el chat activar modo expandido automáticamente
    if (willOpen && window.innerWidth <= 480) {
      setIsExpanded(true);
    }
    setState(prev => ({ ...prev, isMinimized: false }));
  }, [isOpen]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    // En móvil mantener expanded true para la próxima apertura
    // En desktop resetear a false
    setIsExpanded(window.innerWidth > 480 ? false : true);
    setState(prev => ({ ...prev, isMinimized: false }));
  }, []);

  const handleToggleExpand = useCallback(() => {
    setIsExpanded(prev => !prev);
  }, []);

  // Sugerencias para el producto activo (solo cuando hay chip activo)
  const productSuggestions = activeProductContext
    ? buildProductSuggestions(activeProductContext, uiLang)
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
          <div
            className={`${styles.header} ${isHeaderHidden && !isExpanded ? styles.headerHidden : ''}`}
          >
            
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

          {/* ── Contenedor con scroll para mensajes ────────────────────── */}
          <div
            ref={messagesContainerRef}
            className={styles.messagesContainer}
            // className={`${styles.messagesContainer} ${isHeaderHidden && !isExpanded ? styles.moveMessagesContainer : ''}`}

          >
            {/* ── Warming overlay — Case 1: Cloud Run cold start ────────
                Shown when health check takes >1.5s (backend is warming up).
                Disappears automatically once the health check resolves.    */}
            {showWarmingOverlay && (
              <div className={styles.warmingOverlay}>
                <div className={styles.spinner} />
                <p className={styles.warmingText}>
                  {localStorage.getItem('rr_widget_session_id')
                    ? 'Despertando el asistente… Tu sesión anterior está guardada.'
                    : 'Iniciando el asistente…'}
                </p>
              </div>
            )}

            {/* ── Pantalla de bienvenida (estilo Zalando) ──────────────
                Se muestra solo cuando no hay mensajes de usuario todavía.
                Incluye el saludo con nombre si el usuario está logueado.   */}
            {!hasUserMessages && (
              <div className={`${styles.welcomeScreen} ${isExpanded ? styles.h_centerBottom : ''}`}
              >
              {/* <div className={styles.welcomeScreen}> */}
                {isLoggedIn && greetingName && (
                  <div className={styles.personalGreeting}>
                    <span className={styles.personalGreetingHi}>{greetingName} 👋</span>
                    <span className={styles.personalGreetingVerif}>
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"
                        viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                        aria-hidden="true">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        <polyline points="9 12 11 14 15 10" />
                      </svg>
                      {t('verifiedAccount')}
                    </span>
                  </div>
                )}
                <h2 className={styles.welcomeTitle}>
                  {t('welcomeTitle')}
                </h2>
                <p className={styles.welcomeSubtitle}>
                  {t('welcomeSubtitle')}
                </p>

                {/* <div className={styles.aiBubbleWrapper}> */}
                <div className={`${styles.h_hidden} ${isExpanded ? styles.aiBubbleWrapper : ''}`}
                >
                  <AiBubble 
                  size={280} 
                  blur={60}
                  />
                </div>
                <div className={`${styles.h_hidden} ${isExpanded ? styles.aiBubbleWrapper : ''}`}
                  style={{marginTop: '40px'}}
                >
                  <AiBubble 
                  size={200} 
                  blur={0}
                  />
                </div>
                <div className={styles.suggestions} aria-label={t('suggestions')}>
                  <span className={styles.suggestionsLabel}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13"
                      viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                      aria-hidden="true">
                      <path d="M9 18h6" />
                      <path d="M10 22h4" />
                      <path d="M12 2v1" />
                      <path d="M12 7a5 5 0 0 1 5 5c0 2.5-2 4.5-3 6h-4c-1-1.5-3-3.5-3-6a5 5 0 0 1 5-5Z" />
                    </svg>
                    {t('suggestions')}
                  </span>
                  <div className={styles.welcomeSuggestionsWrapper}>
                    {getSuggestionChips(uiLang).map((chip) => (
                        <button key={chip} className={`${styles.welcomeSuggestionChip} ${stylesmessage.bubbleAssistant}`} onClick={() => handleSuggestion(chip, true)}>
                          {chip}
                        </button>
                      ))}
                    </div>
                </div>
                <p className={styles.betaNote}>
                  {t('betaNote')}{' '}
                  <a href="#" className={styles.betaLink} onClick={(e) => { e.preventDefault(); }}>
                    {t('betaLink')}
                  </a>
                </p>
              </div>
            )}

            {/* ── Lista de mensajes — visible cuando hay conversación ── */}
            {hasUserMessages && (
              <MessageList
                messages={state.messages}
                isLoading={state.isLoading}
                isExpanded={isExpanded}
                onChatAbout={handleChatAbout}
                onShowSimilar={handleShowSimilar}
                onSuggestionClick={(text) => handleSendMessage(text, undefined, undefined, true)}
                isServiceDown={serviceStatus === 'down'}
                bottomContent={(serviceStatus === 'down' && !isResuming) || isResuming ? (
                  <>
                    {serviceStatus === 'down' && !isResuming && (
                      <>
                        <div className={styles.divider}>mensajes anteriores inactivos</div>
                        <div className={styles.serviceDownCard}>
                          <div className={styles.serviceDownHeader}>
                            <span>💤</span>
                            <span>El asistente ha entrado en reposo</span>
                          </div>
                          <div className={styles.serviceDownBody}>
                            <p className={styles.serviceDownTitle}>Tu conversación se ha cerrado por falta de actividad</p>
                            <p className={styles.serviceDownSub}>
                              Puedes retomar donde lo dejaste o empezar una nueva conversación.
                            </p>
                            <div className={styles.coldStartActions}>
                              <button className={styles.btnPrimary} onClick={handleLetsContinue}>
                                Let&apos;s continue
                              </button>
                              <button className={styles.btnSecondary} onClick={handleStartNewChat}>
                                Start a new chat
                              </button>
                              <button className={styles.btnGhost} onClick={handleCloseConversation}>
                                Close conversation
                              </button>
                            </div>
                          </div>
                        </div>
                      </>
                    )}
                    {isResuming && (
                      <>
                        <div className={styles.divider}>reanudando conversación</div>
                        {sessionRecap && sessionRecap.length > 0 && (
                          <details className={styles.recapDropdown}>
                            <summary className={styles.recapSummary}>
                              📋 Ver resumen de conversación anterior
                            </summary>
                            <div className={styles.recapBody}>
                              {sessionRecap.map((turn, i) => (
                                <div key={i} className={styles.recapRow}>
                                  <span className={styles.recapRole}>
                                    {turn.role === 'user' ? 'Tú' : 'AI'}
                                  </span>
                                  <span className={styles.recapText}>{turn.content}</span>
                                </div>
                              ))}
                            </div>
                          </details>
                        )}
                        <div className={styles.resumingRow}>
                          <div className={styles.spinnerSmall} />
                          <span className={styles.resumingText}>Resumiendo conversación…</span>
                        </div>
                      </>
                    )}
                  </>
                ) : undefined}
              />
            )}

            {/* Case 2a: Inactivity warning — shown after 15 min of no interaction */}
            {showInactivityWarning && serviceStatus !== 'down' && (
              <div className={styles.inactivityWarning}>
                <button
                  className={styles.inactivityWarningDismiss}
                  onClick={() => setShowInactivityWarning(false)}
                  aria-label="Cerrar aviso"
                >×</button>
                <span className={styles.inactivityWarningTitle}>¿Sigues ahí?</span>
                <span className={styles.inactivityWarningSub}>El chat entrará en reposo si no hay actividad en los próximos 5 minutos.</span>
              </div>
            )}

          </div>

          {/* ── Zona inferior: chip de contexto + sugerencias + input ── */}
          <div className={styles.bottomZone}
            data-chat-input>
            {/* ── Chip de contexto activo — patrón "Let's chat about this item" ──
                Se muestra cuando el usuario ha seleccionado un producto con 💬.
                Incluye imagen en miniatura, título truncado y botón × para cancelar. */}
            {<span className={styles.contextChipWrapper} 
              style={{ borderTop: activeProductContext ? '1px solid rgba(0, 0, 0, 0.1)' : 'none', display: activeProductContext ? 'flex' : 'none' }}
              aria-hidden="true">
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
                  <span className={styles.contextChipLabel}>{t('chatAbout')}</span>
                  <span className={styles.contextChipTitle}>{activeProductContext.title}</span>
                </div>

                {/* Botón × para limpiar el contexto */}
                <button
                  className={styles.contextChipClose}
                  onClick={handleClearContext}
                  aria-label="Quitar producto del contexto"
                  title="Volver al contexto general"
                >
                {/* <svg xmlns="http://www.w3.org/2000/svg" width="20px" viewBox="0 0 24 24" 
                    fill="currentColor" stroke="currentColor" strokeWidth="2" >
                  <path fill-rule="evenodd" clip-rule="evenodd" d="M5.29289 5.29289C5.68342 4.90237 6.31658 4.90237 6.70711 5.29289L12 10.5858L17.2929 5.29289C17.6834 4.90237 18.3166 4.90237 18.7071 5.29289C19.0976 5.68342 19.0976 6.31658 18.7071 6.70711L13.4142 12L18.7071 17.2929C19.0976 17.6834 19.0976 18.3166 18.7071 18.7071C18.3166 19.0976 17.6834 19.0976 17.2929 18.7071L12 13.4142L6.70711 18.7071C6.31658 19.0976 5.68342 19.0976 5.29289 18.7071C4.90237 18.3166 4.90237 17.6834 5.29289 17.2929L10.5858 12L5.29289 6.70711C4.90237 6.31658 4.90237 5.68342 5.29289 5.29289Z" fill="#0F1729"/>
                </svg> */}
              <svg xmlns="http://www.w3.org/2000/svg" x="0px" y="0px" width="24px" height="24px" viewBox="0 0 72 72" fill="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M 19 15 C 17.977 15 16.951875 15.390875 16.171875 16.171875 C 14.609875 17.733875 14.609875 20.266125 16.171875 21.828125 L 30.34375 36 L 16.171875 50.171875 C 14.609875 51.733875 14.609875 54.266125 16.171875 55.828125 C 16.951875 56.608125 17.977 57 19 57 C 20.023 57 21.048125 56.609125 21.828125 55.828125 L 36 41.65625 L 50.171875 55.828125 C 51.731875 57.390125 54.267125 57.390125 55.828125 55.828125 C 57.391125 54.265125 57.391125 51.734875 55.828125 50.171875 L 41.65625 36 L 55.828125 21.828125 C 57.390125 20.266125 57.390125 17.733875 55.828125 16.171875 C 54.268125 14.610875 51.731875 14.609875 50.171875 16.171875 L 36 30.34375 L 21.828125 16.171875 C 21.048125 15.391875 20.023 15 19 15 z"></path>
              </svg>
                </button>
              </div>
            )}

            {/* ── Suggestion chips contextuales al producto activo ──
                Se muestran debajo del chip y desaparecen al enviar el mensaje.
                El usuario puede usarlos o escribir su propio mensaje. */}
            {productSuggestions && (
              <div
                className={`${styles.productSuggestions} ${isExpanded ? styles.h_marginCenter : ''}`}
                // className={styles.productSuggestions}
                // style={{ margin: isExpanded ? '0 auto' : '0' }}
                aria-label="Sugerencias para este producto">
                <span className={styles.productSuggestionsLabel}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    aria-hidden="true">
                    <path d="M9 18h6" />
                    <path d="M10 22h4" />
                    <path d="M12 2v1" />
                    <path d="M12 7a5 5 0 0 1 5 5c0 2.5-2 4.5-3 6h-4c-1-1.5-3-3.5-3-6a5 5 0 0 1 5-5Z" />
                  </svg>
                  {t('suggestions')}
                </span>
                <div className={styles.productSuggestionsRow}>
                  {productSuggestions.map((chip) => (
                    <button
                      key={chip}
                      className={styles.productSuggestionChip}
                      onClick={() => handleSuggestion(chip, false)}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </span>}

            {/* ── Input de texto ── */}
            <MessageInput
              onSendMessage={(messageText) => handleSendMessage(messageText, undefined, undefined, true)}
              onImageUpload={handleImageUpload}
              onOutfitSearch={visualSearchAvailable ? handleOutfitSearch : undefined}
              disabled={state.isLoading || isVisualSearching || isOutfitSearching || showWarmingOverlay || (serviceStatus === 'down' && !isResuming)}
              placeholder={t('inputPlaceholder')}
              visualSearchEnabled={visualSearchAvailable}
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
