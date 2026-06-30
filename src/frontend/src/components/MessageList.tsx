import { useEffect, useRef, useState, useCallback, type ReactNode } from 'react';
import type { Message, OutfitProduct } from '../types/widget';
import { ProductCard } from './ProductCard';
import styles from './MessageList.module.css';

// ─────────────────────────────────────────────────────────────────────────────
// MINI MARKDOWN RENDERER
//
// FIX (27/03/2026): KB documents and personalised responses contain Markdown
// (### headings, - bullet lists, **bold**, etc.).  Rendering them as plain
// text shows the raw syntax characters to the user.
//
// We intentionally avoid adding an external library (marked, react-markdown)
// because this widget is bundled as a single UMD file (~150 KB) and every KB
// added increases cold-start time on Shopify.
//
// This function covers the subset of Markdown actually produced by the backend:
//   • ### / ## / # headings
//   • **bold** and *italic*
//   • - / * unordered list items
//   • Blank lines → paragraph breaks
//
// SECURITY: We never use dangerouslySetInnerHTML with user-supplied content.
// The backend content is sanitised and does not contain raw HTML.
// We do use dangerouslySetInnerHTML here only on our own generated HTML string
// that is built from a controlled whitelist of tags (h3, h2, h1, p, ul, li,
// strong, em).  No script tags, no event handlers, no external URLs.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * renderMarkdown
 *
 * Converts a Markdown string (the subset used by our backend) into a safe
 * HTML string.  Used only with dangerouslySetInnerHTML on assistant messages
 * where the content originates from our own backend (not from the user).
 */
function renderMarkdown(text: string): string {
  if (!text) return '';

  const lines = text.split('\n');
  const htmlLines: string[] = [];
  let inList = false;

  for (const raw of lines) {
    let line = raw;

    // ── Headings ─────────────────────────────────────────────────────────────
    // ### Heading 3
    if (/^###\s+/.test(line)) {
      if (inList) { htmlLines.push('</ul>'); inList = false; }
      const content = escapeHtml(line.replace(/^###\s+/, ''));
      htmlLines.push(`<h3 style="margin:0.75em 0 0.25em;font-size:0.9em;font-weight:600">${content}</h3>`);
      continue;
    }
    // ## Heading 2
    if (/^##\s+/.test(line)) {
      if (inList) { htmlLines.push('</ul>'); inList = false; }
      const content = escapeHtml(line.replace(/^##\s+/, ''));
      htmlLines.push(`<h2 style="margin:0.85em 0 0.3em;font-size:1em;font-weight:600">${content}</h2>`);
      continue;
    }
    // # Heading 1
    if (/^#\s+/.test(line)) {
      if (inList) { htmlLines.push('</ul>'); inList = false; }
      const content = escapeHtml(line.replace(/^#\s+/, ''));
      htmlLines.push(`<h1 style="margin:1em 0 0.3em;font-size:1.1em;font-weight:600">${content}</h1>`);
      continue;
    }

    // ── Unordered list items (- or *) ────────────────────────────────────────
    if (/^[\-\*]\s+/.test(line)) {
      if (!inList) { htmlLines.push('<ul style="margin:0.4em 0;padding-left:1.2em">'); inList = true; }
      const content = inlineMarkdown(line.replace(/^[\-\*]\s+/, ''));
      htmlLines.push(`<li style="margin:0.15em 0">${content}</li>`);
      continue;
    }

    // ── Close list before non-list lines ─────────────────────────────────────
    if (inList) {
      htmlLines.push('</ul>');
      inList = false;
    }

    // ── Blank line → paragraph break ─────────────────────────────────────────
    if (line.trim() === '') {
      htmlLines.push('<br/>');
      continue;
    }

    // ── Regular paragraph line ───────────────────────────────────────────────
    htmlLines.push(`<p style="margin:0.2em 0">${inlineMarkdown(line)}</p>`);
  }

  if (inList) htmlLines.push('</ul>');
  return htmlLines.join('');
}

/** Escape HTML special chars before inserting user-derived text into HTML. */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * inlineMarkdown — process inline **bold** and *italic* within a line.
 * Escapes HTML first to prevent injection, then applies inline transforms.
 */
function inlineMarkdown(line: string): string {
  let s = escapeHtml(line);
  // **bold** → <strong>
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // *italic* (single asterisk, not double)
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  return s;
}

/**
 * containsMarkdown
 *
 * Heuristic: if the string contains any Markdown syntax we care about,
 * render it through renderMarkdown(); otherwise render as plain text.
 * This avoids wrapping every short greeting in a <p> tag.
 */
function containsMarkdown(text: string): boolean {
  return /^#{1,3}\s|^[\-\*]\s|\*\*|\*/m.test(text);
}

// ─────────────────────────────────────────────────────────────────────────────

function generateContextualSuggestions(recommendations: import('../types/widget').ProductRecommendation[], lang: string): string[] {
  const code = lang.split('-')[0].toLowerCase();

  if (!recommendations || recommendations.length === 0) {
    const fallbacks: Record<string, string> = {
      es: '¿Puedo ver más artículos?',
      en: 'Can I see more items?',
      de: 'Kann ich mehr Artikel sehen?',
      fr: 'Puis-je voir plus d\'articles ?',
    };
    return [fallbacks[code] ?? fallbacks['es']];
  }

  const suggestions: string[] = [];

  const categories = Array.from(new Set(recommendations.map(r => r.category).filter(Boolean)));
  const vendors = Array.from(new Set(recommendations.map(r => r.vendor).filter(Boolean)));
  const prices = recommendations.map(r => r.price).filter(p => p > 0);

  // 1. Category-based exploration
  if (categories.length > 0) {
    const category = categories[0].toLowerCase();
    const templates: Record<string, string> = {
      es: `¿Qué combina bien con ${category}?`,
      en: `What goes well with ${category}?`,
      de: `Was passt gut zu ${category}?`,
      fr: `Qu'est-ce qui va bien avec ${category} ?`,
    };
    suggestions.push(templates[code] ?? templates['es']);
  }

  // 2. Brand exploration
  if (vendors.length > 0) {
    const vendor = vendors[0];
    const templates: Record<string, string> = {
      es: `¿Tienes más de ${vendor}?`,
      en: `Do you have more from ${vendor}?`,
      de: `Haben Sie mehr von ${vendor}?`,
      fr: `Avez-vous plus de ${vendor} ?`,
    };
    suggestions.push(templates[code] ?? templates['es']);
  }

  // 3. Alternatives/Variations
  const colorSuggestions: Record<string, string> = {
    es: '¿Los tienen en otros colores?',
    en: 'Do you have these in other colors?',
    de: 'Haben Sie diese in anderen Farben?',
    fr: 'Les avez-vous dans d\'autres couleurs ?',
  };
  suggestions.push(colorSuggestions[code] ?? colorSuggestions['es']);

  // 4. Budget
  if (prices.length > 0) {
    const minPrice = Math.min(...prices);
    const currency = recommendations[0].currency || 'EUR';
    if (minPrice > 20) {
      const budget = Math.floor(minPrice / 10) * 10;
      let formattedBudget = `${budget} ${currency}`;
      try {
        formattedBudget = new Intl.NumberFormat(navigator.language || 'en-US', { style: 'currency', currency: currency, maximumFractionDigits: 0 }).format(budget);
      } catch { /* use fallback */ }
      const templates: Record<string, string> = {
        es: `Muéstrame opciones por debajo de ${formattedBudget}`,
        en: `Show me options under ${formattedBudget}`,
        de: `Zeig mir Optionen unter ${formattedBudget}`,
        fr: `Montre-moi des options à moins de ${formattedBudget}`,
      };
      suggestions.push(templates[code] ?? templates['es']);
    }
  }

  // 5. Fallback category
  if (categories.length > 0 && suggestions.length < 3) {
    const category = categories[0].toLowerCase();
    const templates: Record<string, string> = {
      es: `Muéstrame más ${category}`,
      en: `Show me more ${category}`,
      de: `Zeig mir mehr ${category}`,
      fr: `Montre-moi plus de ${category}`,
    };
    suggestions.push(templates[code] ?? templates['es']);
  }

  // 6. Generic fallback
  if (suggestions.length < 3) {
    const fallbacks: Record<string, string> = {
      es: '¿Puedo ver más artículos?',
      en: 'Can I see more items?',
      de: 'Kann ich mehr Artikel sehen?',
      fr: 'Puis-je voir plus d\'articles ?',
    };
    suggestions.push(fallbacks[code] ?? fallbacks['es']);
  }

  // Deduplicate and limit to 3
  return Array.from(new Set(suggestions)).slice(0, 3);
}

// ── i18n helpers for MessageList UI chrome ─────────────────────────────────
const ML_UI_TEXT: Record<string, Record<string, string>> = {
  es: { suggestions: 'Sugerencias', wasHelpful: '¿Te fue útil?', warmingModel: 'Calentando el modelo…' },
  en: { suggestions: 'Suggestions', wasHelpful: 'Was this helpful?', warmingModel: 'Warming up the model…' },
  de: { suggestions: 'Vorschläge', wasHelpful: 'War das hilfreich?', warmingModel: 'Modell wird aufgewärmt…' },
  fr: { suggestions: 'Suggestions', wasHelpful: 'Cela vous a-t-il aidé ?', warmingModel: 'Réchauffement du modèle…' },
};
function mlT(key: string): string {
  const code = (navigator.language || 'es').split('-')[0].toLowerCase();
  return ML_UI_TEXT[code]?.[key] ?? ML_UI_TEXT['es'][key] ?? '';
}

/**
 * AnimatedReveal -- OPCION A (29/06/2026): efecto de aparicion letra por
 * letra ("Claude style") para el hint "calentando el modelo".
 *
 * Por que: el hint solo aparece tras 3s reales de espera (ver el timer en
 * ChatWidget.tsx) -- en ese punto el usuario ya lleva un rato mirando los
 * tres puntos. Un fade-in instantaneo de todo el texto se siente como un
 * salto brusco; revelar letra por letra comunica visualmente que "algo se
 * esta generando ahora mismo", coherente con la espera real que esta
 * ocurriendo (el warmup del LLM terminando en el backend).
 *
 * Sin librerias externas -- mismo criterio que renderMarkdown() arriba en
 * este archivo: cada caracter es un <span> con animation-delay escalonado
 * (calculado aqui en JS, la animacion CSS vive en .revealLetter). Los
 * espacios se reemplazan por \u00A0 (non-breaking space) para que un span
 * con display:inline-block no los colapse visualmente.
 *
 * Accesibilidad: el texto completo vive en aria-label del span contenedor
 * (rol "status" para que un lector de pantalla lo anuncie una sola vez);
 * los spans de cada letra son aria-hidden para que no se anuncien letra
 * por letra.
 */
function AnimatedReveal({ text, delayStepMs = 22 }: { text: string; delayStepMs?: number }) {
  return (
    <span className={styles.revealContainer} role="status" aria-label={text}>
      {text.split('').map((char, i) => (
        <span
          key={i}
          aria-hidden="true"
          className={styles.revealLetter}
          style={{ animationDelay: `${i * delayStepMs}ms` }}
        >
          {char === ' ' ? '\u00A0' : char}
        </span>
      ))}
    </span>
  );
}

// S1 FASE 4: Etiquetas legibles por categoria de outfit
const OUTFIT_CATEGORY_LABELS: Record<string, Record<string, string>> = {
  dress:     { es: 'Vestidos',   en: 'Dresses',    de: 'Kleider',    fr: 'Robes' },
  enterito:  { es: 'Enteritos',  en: 'Jumpsuits',  de: 'Jumpsuits',  fr: 'Combinaisons' },
  top:       { es: 'Tops',       en: 'Tops',       de: 'Tops',       fr: 'Hauts' },
  bottom:    { es: 'Pantalones', en: 'Bottoms',    de: 'Hosen',      fr: 'Bas' },
  conjunto:  { es: 'Conjuntos',  en: 'Sets',       de: 'Sets',       fr: 'Ensembles' },
  shoes:     { es: 'Zapatos',    en: 'Shoes',      de: 'Schuhe',     fr: 'Chaussures' },
  bag:       { es: 'Carteras',   en: 'Bags',       de: 'Taschen',    fr: 'Sacs' },
  accessory: { es: 'Accesorios', en: 'Accessories', de: 'Accessoires', fr: 'Accessoires' },
  outerwear: { es: 'Capas',      en: 'Outerwear',  de: 'Jacken',     fr: 'Vestes' },
};
function getOutfitLabel(category: string): string {
  const code = (navigator.language || 'es').split('-')[0].toLowerCase();
  return OUTFIT_CATEGORY_LABELS[category]?.[code]
    ?? OUTFIT_CATEGORY_LABELS[category]?.['es']
    ?? category;
}

/**
 * outfitToReco — convierte OutfitProduct a ProductRecommendation para los callbacks
 * del actionBar (onChatAbout / onShowSimilar).
 * OutfitProduct viene del backend con campos ligeramente distintos (product_id vs id).
 */
function outfitToReco(p: OutfitProduct): import('../types/widget').ProductRecommendation {
  return {
    id:          p.product_id,
    title:       p.title,
    description: '',
    price:       p.price ?? 0,
    currency:    p.currency ?? 'CLP',
    category:    p.category ?? '',
    vendor:      '',
    score:       0,
    image_url:   p.image_url,
    url:         p.url || (p.handle ? `/products/${p.handle}` : undefined),
  };
}

/**
 * OutfitCardSlider — S1 FASE 4 (rework 14/05/2026).
 *
 * Muestra los productos de una categoría de outfit como un slider tipo "card deck":
 *   • Una carta visible a la vez (el slide activo)
 *   • Cartas fantasma detrás creando efecto de mazo (puro CSS, sin librerías)
 *   • Navegación: tap en mitad izquierda = anterior, mitad derecha = siguiente
 *   • Dots indicadores de posición debajo del mazo
 *   • ActionBar idéntica a ProductCard: Añadir al carrito + Ver similares + Hablar sobre
 *
 * Compatibilidad con la arquitectura:
 *   OutfitProduct → outfitToReco() → ProductRecommendation para los callbacks.
 */
function OutfitCardSlider({
  category,
  products,
  onChatAbout,
  onShowSimilar,
}: {
  category:      string;
  products:      OutfitProduct[];
  onChatAbout?:  (product: import('../types/widget').ProductRecommendation) => void;
  onShowSimilar?: (product: import('../types/widget').ProductRecommendation) => void;
}) {
  const [activeIdx, setActiveIdx] = useState(0);
  // Altura medida de la carta activa: los ghost cards la necesitan porque son
  // divs vacíos y position:absolute sin height explícito = height:0 cuando el
  // contenedor es height:auto.

  const label = getOutfitLabel(category);
  const lc    = (navigator.language || 'es').split('-')[0].toLowerCase();
  const deckProducts = products.slice(0, 3);
  const total = deckProducts.length;
  const active = deckProducts[activeIdx];

  // Formatear precio con Intl.NumberFormat (locale-aware)
  const formatPrice = (price?: number, currency?: string) => {
    if (!price) return null;
    try {
      return new Intl.NumberFormat(navigator.language || 'es', {
        style: 'currency', currency: currency || 'CLP', maximumFractionDigits: 0,
      }).format(price);
    } catch { return `${price} ${currency || ''}`.trim(); }
  };

  // Mide el alto de la carta activa tras cada render para pasárselo a los ghost cards.
  // Los ghost cards son divs vacíos; sin height explícito tienen height:0 en
  // contenedores con height:auto.
  useEffect(() => {
    if (activeIdx >= total) {
      setActiveIdx(0);
    }
  }, [activeIdx, total]);

  // Navegar al producto en Shopify al hacer click en la carta
  const handleCardClick = useCallback((e: React.MouseEvent) => {
    // Ignorar clicks en los botones del actionBar (tienen stopPropagation)
    const target = e.target as HTMLElement;
    if (target.closest('button')) return;
    if (active.handle) {
      const url = active.url || `/products/${active.handle}`;
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }, [active]);

  const navigate = useCallback((newDir: 1 | -1) => {
    if (total <= 1) return;
    // Breve delay para animar la salida antes de cambiar el índice
    setActiveIdx(i => (i + newDir + total) % total);
  }, [total]);

  // Touch swipe: deslizar horizontalmente para navegar
  const touchStartX = useRef<number | null>(null);
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  };
  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const delta = e.changedTouches[0].clientX - touchStartX.current;
    if (Math.abs(delta) > 30) {
      navigate(delta < 0 ? 1 : -1);  // deslizar izquierda = siguiente
    }
    touchStartX.current = null;
  };

  // ── Estilos de la carta activa con transición ───────────────────────────────
  const visibleStack = deckProducts
    .map((product, index) => ({
      product,
      offset: (index - activeIdx + total) % total,
    }))
    .filter(({ offset }) => offset < 3)
    .sort((a, b) => b.offset - a.offset);

  const cardTransitionStyle: React.CSSProperties = { display: 'none' };
  const ghostStyle1: React.CSSProperties = { display: 'none' };
  const ghostStyle2: React.CSSProperties = { display: 'none' };
  const ghostStyle3: React.CSSProperties = { display: 'none' };

  // ── Estilos de las cartas fantasma del mazo ──────────────────────────────────
  // Enfoque: réplicas de altura completa de la carta activa, posicionadas con
  // top/bottom relativo al paddingBox del contenedor (paddingBottom: 22px).
  // overflow:hidden en el contenedor las recorta mostrando solo el "borde inferior"
  // que sobresale de la carta activa → efecto de mazo real.
  //
  // Matemática con paddingBottom=22px (H = alto de la carta activa):
  //   element_height = container_height - top - bottom = (H+22) - top - bottom
  //   element_bottom  = H + 22 - bottom
  //   peek            = element_bottom - H = 22 - bottom
  //
  // Ghost 1 (más cercana):  top:6  bottom:16 → peek=6px,  inset=5px
  // Ghost 2 (media):        top:12 bottom:10 → peek=12px, inset=10px
  // Ghost 3 (más lejana):   top:18 bottom:4  → peek=18px, inset=15px
  // Ghost cards: réplicas de altura completa de la carta activa, con top/bottom
  // calculados para que exactamente X px sobresalgan por debajo de la carta activa.
  // Sin overflow:hidden en el contenedor → viven dentro del paddingBottom (22px).
  //
  // Matemática (paddingBottom=22, H=alto carta activa):
  //   ghost_bottom_edge = H + 22 - bottom_value
  //   peek              = ghost_bottom_edge - H = 22 - bottom_value
  //   ghost_height      = H + 22 - top - bottom  = H  (siempre que top+bottom=22)
  //
  // Ghost cards con altura explícita medida desde la carta activa.
  // peek = top offset → ghost_bottom = top + ghostH → sobresale (top)px bajo la carta activa.

  const renderStackCard = (product: OutfitProduct, offset: number) => {
    const isActive = offset === 0;
    const translate = offset * 8;
    const translateX = offset * 11; // Ghost 1 se desplaza ligeramente a la izquierda, Ghost 2 y 3 a la derecha
    const scale = 1 - offset * 0.045;

    return (
      <div
        key={product.product_id || `${category}-${offset}`}
        role={isActive && product.handle ? 'button' : 'article'}
        tabIndex={isActive && product.handle ? 0 : undefined}
        aria-hidden={!isActive}
        aria-label={isActive && product.handle ? `Ver ${product.title}` : product.title}
        onKeyDown={isActive ? e => e.key === 'Enter' && handleCardClick(e as any) : undefined}
        onClick={isActive ? handleCardClick : undefined}
        onTouchStart={isActive ? handleTouchStart : undefined}
        onTouchEnd={isActive ? handleTouchEnd : undefined}
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 10 - offset,
          background: 'var(--surface, #fff)',
          // background:isActive? 'var(--surface, #fff)' : 'var(--surface, #1c1c1ce5)',
          borderRadius: '10px',
          border: '1px solid var(--border, #606369)',
          overflow: 'hidden',
          cursor: isActive && product.handle ? 'pointer' : 'default',
          boxShadow: isActive
            ? '0 8px 18px rgba(0,0,0,0.12)'
            : `0 ${4 + offset * 2}px ${12 + offset * 4}px rgba(0,0,0,${0.10 - offset * 0.015})`,
          display: 'flex',
          flexDirection: 'column',
          pointerEvents: isActive ? 'auto' : 'none',
          transform: `translate3d(${translateX}px, ${translate}px, ${-offset * 80}px) rotate(${0}deg) scale(${scale})`,
          transformOrigin: 'center bottom',
          transition: 'transform 280ms cubic-bezier(.22,.61,.36,1), opacity 280ms cubic-bezier(.22,.61,.36,1), box-shadow 280ms cubic-bezier(.22,.61,.36,1)',
          opacity: 1 - offset * 0.12,
          willChange: 'transform, opacity',
        }}
      >
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.title}
            loading="lazy"
            style={{
              width: '100%',
              height: '175px',
              objectFit: 'cover',
              display: 'block',
            }}
          />
        ) : (
          <div style={{
            width: '100%', height: '175px',
            background: 'linear-gradient(135deg, #f3ede6, #e8ddd4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '32px',
          }}>
            {category === 'shoes' ? 'ðŸ‘ ' : category === 'bag' ? 'ðŸ‘œ'
              : category === 'accessory' ? 'âœ¨' : category === 'outerwear' ? 'ðŸ§¥' : 'ðŸ‘—'}
          </div>
        )}

        <div style={{ padding: '8px 10px 4px', flex: 1, minHeight: '60px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div style={{
            fontSize: '11.5px',
            fontWeight: 600,
            lineHeight: 1.3,
            color: 'var(--text-primary, #1c1c1c)',
            overflow: 'hidden',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            marginBottom: '4px',
          }}>
            {product.title}
          </div>
          {product.price != null && product.price > 0 && (
            <div style={{
              fontSize: '12px',
              fontWeight: 700,
              color: 'var(--primary, #ec4899)',
            }}>
              {formatPrice(product.price, product.currency)}
            </div>
          )}
        </div>

        <div
          onClick={e => e.stopPropagation()}
          style={{
            display: 'flex',
            borderTop: '1px solid rgba(0,0,0,0.06)',
            marginTop: '4px',
            opacity: isActive ? 1 : 0.55,
          }}
        >
          <button
            disabled
            title={lc === 'en' ? 'Add to cart (coming soon)' : 'AÃ±adir al carrito (prÃ³ximamente)'}
            aria-label={lc === 'en' ? 'Add to cart (coming soon)' : 'AÃ±adir al carrito'}
            style={{
              flex: 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '7px 4px',
              border: 'none',
              background: '#2b2b2be5',
              color: '#747474',
              cursor: 'not-allowed',
            }}
          >
            <svg viewBox="0 0 24 24" width="18" fill="currentColor" aria-hidden="true">
              <path d="M21.193 8.712a2.984 2.984 0 0 0-2.986-2.726h-.952v-.751a5.255 5.255 0 0 0-10.51 0v.75h-.951a2.983 2.983 0 0 0-2.986 2.727L1.715 20.73q-.012.135-.012.27A3 3 0 0 0 4.7 24h.005l14.599-.026q.133 0 .265-.012a3 3 0 0 0 2.715-3.258zM8.246 5.235a3.754 3.754 0 0 1 7.508 0v.75H8.246zm11.056 17.238-14.599.025h-.002q-.067 0-.135-.006a1.496 1.496 0 0 1-1.355-1.625l1.093-12.02a1.49 1.49 0 0 1 1.49-1.36h.95V9.74a.75.75 0 0 0 1.502 0V7.487h7.508V9.74c0 .415.336.75.75.75h.002a.75.75 0 0 0 .75-.75V7.487h.951a1.49 1.49 0 0 1 1.49 1.361l1.092 11.993q.006.067.007.133a1.496 1.496 0 0 1-1.494 1.499"></path>
            </svg>
          </button>

          {onShowSimilar && (
            <button
              title={lc === 'en' ? 'Show similar products' : 'Ver productos similares'}
              aria-label={`${lc === 'en' ? 'Similar products to' : 'Similares a'} ${product.title}`}
              onClick={e => { e.stopPropagation(); onShowSimilar(outfitToReco(product)); }}
              style={{
                flex: 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '7px 4px',
                border: 'none', borderLeft: '1px solid rgba(0,0,0,0.06)',
                background: 'transparent',
                color: '#7c7c7c',
                cursor: 'pointer',
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.background = '#f4f4f4';
                (e.currentTarget as HTMLElement).style.color = '#1c1c1c';
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.background = 'transparent';
                (e.currentTarget as HTMLElement).style.color = '#7c7c7c';
              }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="17"
                fill="currentColor" aria-hidden="true">
                <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0" />
              </svg>
            </button>
          )}

          {onChatAbout && (
            <button
              title={lc === 'en' ? 'Chat about this item' : 'Hablar sobre este producto'}
              aria-label={`${lc === 'en' ? 'Chat about' : 'Hablar sobre'} ${product.title}`}
              onClick={e => { e.stopPropagation(); onChatAbout(outfitToReco(product)); }}
              style={{
                flex: 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '7px 4px',
                border: 'none', borderLeft: '1px solid rgba(0,0,0,0.06)',
                background: 'transparent',
                color: '#7c7c7c',
                cursor: 'pointer',
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.background = '#1c1c1c';
                (e.currentTarget as HTMLElement).style.color = '#fff';
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.background = 'transparent';
                (e.currentTarget as HTMLElement).style.color = '#7c7c7c';
              }}
            >
              <svg height="18" viewBox="0 0 24 24" width="18" fill="currentColor"
                xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path d="M16 2H4a3 3 0 00-3 3v8a3 3 0 003 3h1v2.14a.8.8 0 001.188.7L11.3 16H16a3 3 0 003-3V5a3 3 0 00-3-3ZM4 4h12a1 1 0 011 1v8a1 1 0 01-1 1h-5.218l-.452.252L7 16.1V14H4a1 1 0 01-1-1V5a1 1 0 011-1Zm17 2.174A3 3 0 0123 9v8a3 3 0 01-2.846 2.996L20 20v2.14a.8.8 0 01-1.189.7L13.701 20H8.216l3.6-2h2.402l.453.252L18 20.101V18.05l1.95-.05.113-.003A1 1 0 0021 17V6.174Z" />
              </svg>
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div style={{
      minWidth: '148px',
      maxWidth: '148px',
      display:  'flex',
      flexDirection: 'column',
      gap: '16px',
      userSelect: 'none',
    }}>

      {/* ─ Cabecera de categoría ───────────────────────────────── */}
      <div style={{
        fontSize: '10px',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.07em',
        color: 'var(--text-secondary, #6b7280)',
        paddingBottom: '4px',
        borderBottom: '2px solid var(--primary, #ec4899)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <span>{label}</span>
        {total > 1 && (
          <span style={{ fontSize: '9px', fontWeight: 400, opacity: 0.6 }}>
            {total}
          </span>
        )}
      </div>

      {/* ─ Área de la carta con efecto de mazo ──────────────────── */}
      {/* Sin overflow:hidden — los ghost cards viven dentro del paddingBottom */}
      <div style={{
        position: 'relative',
        height: '286px',
        paddingRight: total > 1 ? '18px' : 0,
        paddingBottom: total > 1 ? '18px' : 0,
        perspective: '700px',
        perspectiveOrigin: 'top right',

      }}>
        {visibleStack.map(({ product, offset }) => renderStackCard(product, offset))}
      </div>
      <div style={{ display: 'none' }}>

        {/* Cartas fantasma — réplicas de altura completa, recortadas por overflow:hidden */}
        {total > 2 && <div style={ghostStyle3} />}
        {total > 1 && <div style={ghostStyle2} />}
        {total > 0 && <div style={ghostStyle1} />}

        {/* Carta activa — toda la lógica de interacción */}
        <div
          role={active.handle ? 'button' : 'article'}
          tabIndex={active.handle ? 0 : undefined}
          aria-label={active.handle ? `Ver ${active.title}` : active.title}
          onKeyDown={e => e.key === 'Enter' && handleCardClick(e as any)}
          onClick={handleCardClick}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          style={{
            position: 'relative',
            zIndex:   3,
            background: 'var(--surface, #fff)',
            borderRadius: '10px',
            border:  '1px solid var(--border, #e5e7eb)',
            overflow: 'hidden',
            cursor:  active.handle ? 'pointer' : 'default',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
            display: 'flex',
            flexDirection: 'column',
            ...cardTransitionStyle,
          }}
        >
          {/* Imagen */}
          {active.image_url ? (
            <img
              src={active.image_url}
              alt={active.title}
              loading="lazy"
              style={{
                width: '100%',
                height: '175px',
                objectFit: 'cover',
                display: 'block',
              }}
            />
          ) : (
            <div style={{
              width: '100%', height: '175px',
              background: 'linear-gradient(135deg, #f3ede6, #e8ddd4)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '32px',
            }}>
              {category === 'shoes' ? '👠' : category === 'bag' ? '👜'
                : category === 'accessory' ? '✨' : category === 'outerwear' ? '🧥' : '👗'}
            </div>
          )}

          {/* Info: título + precio — altura fija para que todas las cartas sean iguales */}
          <div style={{ padding: '8px 10px 4px', flex: 1, minHeight: '60px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div style={{
              fontSize: '11.5px',
              fontWeight: 600,
              lineHeight: 1.3,
              color: 'var(--text-primary, #1c1c1c)',
              overflow: 'hidden',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              marginBottom: '4px',
            }}>
              {active.title}
            </div>
            {active.price != null && active.price > 0 && (
              <div style={{
                fontSize: '12px',
                fontWeight: 700,
                color: 'var(--primary, #ec4899)',
              }}>
                {formatPrice(active.price, active.currency)}
              </div>
            )}
          </div>

          {/* ActionBar — idéntica a ProductCard (3 botones) */}
          <div
            onClick={e => e.stopPropagation()}
            style={{
              display:    'flex',
              borderTop:  '1px solid rgba(0,0,0,0.06)',
              marginTop:  '4px',
            }}
          >
            {/* Añadir al carrito (deshabilitado) */}
            <button
              disabled
              title={lc === 'en' ? 'Add to cart (coming soon)' : 'Añadir al carrito (próximamente)'}
              aria-label={lc === 'en' ? 'Add to cart (coming soon)' : 'Añadir al carrito'}
              style={{
                flex: 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '7px 4px',
                border: 'none',
                background: '#2b2b2be5',
                color: '#747474',
                cursor: 'not-allowed',
              }}
            >
              <svg viewBox="0 0 24 24" width="18" fill="currentColor" aria-hidden="true">
                <path d="M21.193 8.712a2.984 2.984 0 0 0-2.986-2.726h-.952v-.751a5.255 5.255 0 0 0-10.51 0v.75h-.951a2.983 2.983 0 0 0-2.986 2.727L1.715 20.73q-.012.135-.012.27A3 3 0 0 0 4.7 24h.005l14.599-.026q.133 0 .265-.012a3 3 0 0 0 2.715-3.258zM8.246 5.235a3.754 3.754 0 0 1 7.508 0v.75H8.246zm11.056 17.238-14.599.025h-.002q-.067 0-.135-.006a1.496 1.496 0 0 1-1.355-1.625l1.093-12.02a1.49 1.49 0 0 1 1.49-1.36h.95V9.74a.75.75 0 0 0 1.502 0V7.487h7.508V9.74c0 .415.336.75.75.75h.002a.75.75 0 0 0 .75-.75V7.487h.951a1.49 1.49 0 0 1 1.49 1.361l1.092 11.993q.006.067.007.133a1.496 1.496 0 0 1-1.494 1.499"></path>
              </svg>
            </button>

            {/* Ver productos similares */}
            {onShowSimilar && (
              <button
                title={lc === 'en' ? 'Show similar products' : 'Ver productos similares'}
                aria-label={`${lc === 'en' ? 'Similar products to' : 'Similares a'} ${active.title}`}
                onClick={e => { e.stopPropagation(); onShowSimilar(outfitToReco(active)); }}
                style={{
                  flex: 1,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '7px 4px',
                  border: 'none', borderLeft: '1px solid rgba(0,0,0,0.06)',
                  background: 'transparent',
                  color: '#7c7c7c',
                  cursor: 'pointer',
                  transition: 'background 0.15s, color 0.15s',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.background = '#f4f4f4';
                  (e.currentTarget as HTMLElement).style.color = '#1c1c1c';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                  (e.currentTarget as HTMLElement).style.color = '#7c7c7c';
                }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="17"
                  fill="currentColor" aria-hidden="true">
                  <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0" />
                </svg>
              </button>
            )}

            {/* Hablar sobre este producto */}
            {onChatAbout && (
              <button
                title={lc === 'en' ? 'Chat about this item' : 'Hablar sobre este producto'}
                aria-label={`${lc === 'en' ? 'Chat about' : 'Hablar sobre'} ${active.title}`}
                onClick={e => { e.stopPropagation(); onChatAbout(outfitToReco(active)); }}
                style={{
                  flex: 1,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '7px 4px',
                  border: 'none', borderLeft: '1px solid rgba(0,0,0,0.06)',
                  background: 'transparent',
                  color: '#7c7c7c',
                  cursor: 'pointer',
                  transition: 'background 0.15s, color 0.15s',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.background = '#1c1c1c';
                  (e.currentTarget as HTMLElement).style.color = '#fff';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                  (e.currentTarget as HTMLElement).style.color = '#7c7c7c';
                }}
              >
                <svg height="18" viewBox="0 0 24 24" width="18" fill="currentColor"
                  xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M16 2H4a3 3 0 00-3 3v8a3 3 0 003 3h1v2.14a.8.8 0 001.188.7L11.3 16H16a3 3 0 003-3V5a3 3 0 00-3-3ZM4 4h12a1 1 0 011 1v8a1 1 0 01-1 1h-5.218l-.452.252L7 16.1V14H4a1 1 0 01-1-1V5a1 1 0 011-1Zm17 2.174A3 3 0 0123 9v8a3 3 0 01-2.846 2.996L20 20v2.14a.8.8 0 01-1.189.7L13.701 20H8.216l3.6-2h2.402l.453.252L18 20.101V18.05l1.95-.05.113-.003A1 1 0 0021 17V6.174Z" />
                </svg>
              </button>
            )}
          </div>

        </div>
      </div>

      {/* ─ Navegación con flechas ───────────────────────────────── */}
      {total > 1 && (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '6px',
          marginTop: '2px',
        }}>
          <button
            onClick={() => navigate(-1)}
            aria-label={lc === 'en' ? 'Previous' : 'Anterior'}
            style={{
              width: '28px', height: '28px',
              borderRadius: '6px',
              background: 'var(--surface, #fff)',
              border: '1px solid var(--border, #e5e7eb)',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#6b7280',
              padding: 0,
              fontSize: '16px',
              lineHeight: 1,
              // boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              transition: 'background 0.15s, color 0.15s',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.background = '#f3f4f6';
              (e.currentTarget as HTMLElement).style.color = '#1c1c1c';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.background = 'var(--surface, #fff)';
              (e.currentTarget as HTMLElement).style.color = '#6b7280';
            }}
          >
            ‹
          </button>
          <span style={{ fontSize: '11px', color: '#6b7280', minWidth: '28px', textAlign: 'center' }}>
            {activeIdx + 1}/{total}
          </span>
          <button
            onClick={() => navigate(1)}
            aria-label={lc === 'en' ? 'Next' : 'Siguiente'}
            style={{
              width: '28px', height: '28px',
              borderRadius: '6px',
              background: 'var(--surface, #fff)',
              border: '1px solid var(--border, #e5e7eb)',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#6b7280',
              padding: 0,
              fontSize: '16px',
              lineHeight: 1,
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              transition: 'background 0.15s, color 0.15s',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.background = '#f3f4f6';
              (e.currentTarget as HTMLElement).style.color = '#1c1c1c';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.background = 'var(--surface, #fff)';
              (e.currentTarget as HTMLElement).style.color = '#6b7280';
            }}
          >
            ›
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * OutfitPanel — S1 FASE 4: Panel horizontal de outfit con scroll.
 * Renderiza un OutfitCardSlider por cada categoría encontrada.
 * Recibe los callbacks de acción para propagarlos a cada carta.
 */
function OutfitPanel({
  outfitResult,
  onChatAbout,
  onShowSimilar,
  isExpanded,
}: {
  outfitResult:  NonNullable<Message['outfitResult']>;
  onChatAbout?:  (product: import('../types/widget').ProductRecommendation) => void;
  onShowSimilar?: (product: import('../types/widget').ProductRecommendation) => void;
  isExpanded?: boolean;
}) {
  const categories = Object.entries(outfitResult.outfit ?? {})
    .filter(([, prods]) => prods.length > 0);
  if (categories.length === 0) return null;

  return (
    <div style={{
      marginTop: '10px',
      overflowX: 'auto',
      paddingBottom: '8px',
      WebkitOverflowScrolling: 'touch',
      // scrollbarWidth: 'thin',
      scrollbarWidth: 'auto',
    }}>
      {/* <div style={{ display: 'flex', gap: '24px', width: 'max-content', alignItems: 'flex-start', paddingBottom: '4px' }}> */}
      <div style={{ display: 'flex', gap: '24px', width: `${isExpanded ? '100%' : 'max-content'}`, flexWrap: 'wrap', alignItems: 'flex-start', paddingBottom: '4px' }}>
        {categories.map(([category, products]) => (
          <OutfitCardSlider
            key={category}
            category={category}
            products={products}
            onChatAbout={onChatAbout}
            onShowSimilar={onShowSimilar}
          />
        ))}
      </div>
    </div>
  );
}

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  /**
   * onChatAbout — callback propagado desde ChatWidget a cada ProductCard.
   * Activa el chip de contexto en el input (Sabor 3).
   */
  onChatAbout?: (product: import('../types/widget').ProductRecommendation) => void;
  /**
   * onShowSimilar — callback propagado desde ChatWidget a cada ProductCard.
   * Envía automáticamente una petición de productos similares (Sabor 2).
   */
  onShowSimilar?: (product: import('../types/widget').ProductRecommendation) => void;
  onSuggestionClick?: (text: string) => void;
  isExpanded?: boolean;
  /** isServiceDown — when true, all message bubbles are faded (Case 2b) */
  isServiceDown?: boolean;
  /** bottomContent — rendered at the bottom of the scroll area (e.g., service-down card) */
  bottomContent?: ReactNode;
  /**
   * warmingHint -- OPCION A (29/06/2026): true cuando isLoading lleva mas
   * de 3s seguidos (timer en ChatWidget.tsx). Muestra el texto "Calentando
   * el modelo..." debajo de los tres puntos del indicador de escritura,
   * en vez de tapar el chat con el showWarmingOverlay completo -- ese
   * overlay sigue reservado solo para la apertura inicial del chat.
   */
  warmingHint?: boolean;
}

export function MessageList({ messages, isLoading, isExpanded, onChatAbout, onShowSimilar, onSuggestionClick, isServiceDown, bottomContent, warmingHint }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [expandedKbId, setExpandedKbId] = useState<string | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className={styles.list}>
      {messages.map((message, index) => {
        const isLastMessage = index === messages.length - 1;
        return (
          <div
            key={message.id}
            className={`${styles.row} ${message.type === 'user' ? styles.rowUser : styles.rowAssistant
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
              {/*
             * CHIP DE SUGERENCIA — elemento separado, FUERA de la burbuja.
             *
             * Requisito: el chip debe poder estilizarse independientemente
             * del mensaje. Tenerlo fuera de .bubble permite cambiar su
             * font-size, color, padding, etc. sin heredar ni afectar los
             * estilos de .bubbleUser.
             *
             * Estructura final:
             *   <div messageContent>
             *     <span suggestionChipBadge>  ← chip, clase propia
             *     <div bubble bubbleUser>      ← mensaje, clase propia
             *
             * Solo se renderiza para mensajes de usuario con chip.
             */}
              {message.type === 'user' && message.suggestionChip && (
                <div className={styles.suggestionChip}>
                  <div className={styles.suggestionChipBadge}>
                    {message.suggestionChip.image_url && (
                      <img
                        src={message.suggestionChip.image_url}
                        alt=""
                        className={styles.suggestionChipImg}
                        aria-hidden="true"
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    )}
                    <p>{message.suggestionChip.label}</p>
                  </div>
                </div>
              )}

              {/* Burbuja principal
                FIX (27/03/2026): User messages are always plain text.
                Assistant messages may contain Markdown (KB responses, personalised
                responses with lists).  We detect Markdown and use
                dangerouslySetInnerHTML only on assistant messages where the
                content comes from our controlled backend — never from the user.
            */}
              <div
                className={`${styles.bubble} ${message.type === 'user'
                  ? `${styles.bubbleUser} ${isServiceDown ? styles.bubbleInactive : ''}`
                  : message.type === 'error'
                    ? styles.bubbleError
                    : `${styles.bubbleAssistant} ${isServiceDown ? styles.bubbleInactive : ''}`
                  }`}
              >

                {message.type === 'user' || message.type === 'error' ? (
                  /*
                   * Mensajes de usuario: siempre mostrar el texto plano.
                   * El chip (si existe) ya se renderizó como elemento separado
                   * encima de esta burbuja con su propia clase CSS.
                   *
                   * IMPORTANTE: chip.label = título del PRODUCTO (no la query).
                   * message.content = texto de la PREGUNTA del usuario.
                   * Son siempre distintos — no hay riesgo de duplicado.
                   */
                  message.content || null
                ) : containsMarkdown(message.content) ? (
                  // Markdown detected in assistant message — render as safe HTML
                  <span
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
                  />
                ) : (
                  // Short assistant messages with no Markdown — plain text is cleaner
                  message.content
                )}
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
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                    <polyline points="10 9 9 9 8 9" />
                  </svg>
                  {expandedKbId === message.id ? 'Ocultar documento' : 'Ver política completa'}
                </button>
              )}

              {/* Panel expandible con el documento KB completo
                FIX (27/03/2026): The KB document also contains Markdown.
                Apply the same Markdown rendering logic here. */}
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
                    {containsMarkdown(message.kb_document) ? (
                      <span
                        dangerouslySetInnerHTML={{
                          __html: renderMarkdown(message.kb_document),
                        }}
                      />
                    ) : (
                      message.kb_document
                    )}
                  </div>
                </div>
              )}

              {/* Tarjetas de productos recomendados */}
              {message.recommendations && message.recommendations.length > 0 && (
                <div className={isServiceDown ? styles.bubbleInactive : ''}>
                  <span className={styles.recoLabel}>Recomendado para ti</span>
                  <div className={`${styles.productsList} ${isExpanded ? styles.productsListExpanded : ''}`}>
                    {message.recommendations.slice(0, 8).map((product) => (
                      <ProductCard
                        key={product.id}
                        product={product}
                        onChatAbout={onChatAbout}
                        onShowSimilar={onShowSimilar}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* S1 FASE 4: Panel de outfit categorizado con slider por categoría */}
              {message.outfitResult && (
                <OutfitPanel
                  outfitResult={message.outfitResult}
                  isExpanded={isExpanded}
                  onChatAbout={onChatAbout}
                  onShowSimilar={onShowSimilar}
                />
              )}

              {/* Sugerencias contextuales y feedback (solo en el último mensaje del asistente) */}
              {isLastMessage && message.type === 'assistant' && (
                <div className={styles.postMessageActions}>
                  {message.recommendations && message.recommendations.length > 0 && (
                    <div className={styles.categorySuggestions}>
                      <div className={styles.suggestionsHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
                        </svg>
                        {mlT('suggestions')}
                      </div>
                      <div className={styles.suggestionsList}>
                        {generateContextualSuggestions(message.recommendations, navigator.language || 'es').map(suggestion => (
                          <button
                            key={suggestion}
                            className={styles.suggestionPill}
                            onClick={() => onSuggestionClick && onSuggestionClick(suggestion)}
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className={styles.feedbackSection}>
                    <span>{mlT('wasHelpful')}</span>
                    <button className={styles.feedbackBtn} aria-label="Helpful">
                      <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" >
                        <path d="M24 14.596a2.47 2.47 0 0 0-1.256-2.145c.24-.38.384-.827.386-1.31a2.48 2.48 0 0 0-2.475-2.488H12.53a6.94 6.94 0 0 0-.134-7.589A2.6 2.6 0 0 0 10.32 0a2.536 2.536 0 0 0-2.53 2.533V4.9l-3.175 6.35H.75A.75.75 0 0 0 0 12v8.654c.001.414.337.75.75.75h3.663A3.35 3.35 0 0 0 7.672 24H19.79a2.48 2.48 0 0 0 2.48-2.48c0-.487-.145-.938-.387-1.321a2.47 2.47 0 0 0 1.247-2.135 2.46 2.46 0 0 0-.385-1.322A2.47 2.47 0 0 0 24 14.596m-3.345 4.443h-4.336a.98.98 0 1 1 .008-1.962h4.328a.98.98 0 0 1 0 1.962m.864-3.462h-5.192a.98.98 0 1 1 0-1.961h5.192a.98.98 0 1 1 0 1.961m.113-4.446a.98.98 0 0 1-.977.985H16.32a.981.981 0 1 1 .007-1.963h4.328a.98.98 0 0 1 .977.978M5.827 20.654v-.001a.75.75 0 0 0-.75-.75H1.5V12.75h3.577a.75.75 0 0 0 .671-.415l3.461-6.923a.76.76 0 0 0 .08-.335V2.533c0-.57.462-1.033 1.032-1.033.345.006.666.175.868.455 2.367 3.204-.512 6.822-.636 6.975a.75.75 0 0 0 .581 1.223h2.7c-.128 3.194-1.777 6.29-5.295 6.29a.75.75 0 0 0 0 1.5c2.268 0 4.147-1.08 5.353-2.892.091.49.325.93.658 1.272a2.47 2.47 0 0 0 .001 3.469 2.47 2.47 0 0 0-.502 2.708H7.673a1.85 1.85 0 0 1-1.846-1.846M19.79 22.5h-3.462a.98.98 0 1 1 0-1.961h3.462a.98.98 0 0 1 0 1.961"></path>
                      </svg>
                    </button>
                    <button className={styles.feedbackBtn} aria-label="Not helpful">
                      <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor">
                        <path d="M22.744 7.258a2.46 2.46 0 0 0 .385-1.322A2.47 2.47 0 0 0 21.882 3.8c.242-.383.387-.834.387-1.32A2.48 2.48 0 0 0 19.79 0H7.673a3.35 3.35 0 0 0-3.261 2.596H.75a.75.75 0 0 0-.75.75V12c0 .414.335.75.749.75h3.865L7.79 19.1v2.367A2.536 2.536 0 0 0 10.32 24a2.6 2.6 0 0 0 2.075-1.064 6.94 6.94 0 0 0 .134-7.59h8.125a2.48 2.48 0 0 0 2.475-2.487 2.46 2.46 0 0 0-.386-1.31A2.47 2.47 0 0 0 24 9.404a2.47 2.47 0 0 0-1.256-2.146m-1.113-1.312a.98.98 0 0 1-.976.977h-4.328a.98.98 0 1 1-.008-1.962h4.336a.98.98 0 0 1 .976.985m.869 3.457a.98.98 0 0 1-.981.981h-5.192a.98.98 0 1 1 0-1.961h5.192a.98.98 0 0 1 .98.98m-1.845 4.444h-4.328a.981.981 0 0 1-.007-1.963h4.335a.981.981 0 0 1 0 1.963M7.673 1.5h6.376a2.47 2.47 0 0 0 .502 2.708 2.47 2.47 0 0 0 0 3.469 2.47 2.47 0 0 0-.659 1.272c-1.206-1.811-3.085-2.891-5.353-2.891a.75.75 0 0 0 0 1.5c3.518 0 5.167 3.095 5.294 6.288h-2.699a.75.75 0 0 0-.581 1.224c.124.153 3.003 3.77.636 6.975-.202.28-.523.449-.868.455-.57 0-1.032-.462-1.032-1.033v-2.544a.76.76 0 0 0-.08-.336l-3.461-6.922a.75.75 0 0 0-.67-.415H1.5V4.096h3.577a.75.75 0 0 0 .75-.749c0-1.02.827-1.846 1.846-1.847m13.096.98a.98.98 0 0 1-.98.981h-3.462a.98.98 0 1 1 0-1.961h3.462a.98.98 0 0 1 .98.98"></path>
                      </svg>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}

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
              color="white"
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
          <div className={styles.typingColumn}>
            <div className={styles.typingBubble} aria-label="El asistente está escribiendo">
              <span className={styles.typingDot} />
              <span className={styles.typingDot} />
              <span className={styles.typingDot} />
            </div>
            {/* OPCION A (29/06/2026): hint inline -- solo tras 3s reales de
                espera (ver useEffect en ChatWidget.tsx). No tapa el chat
                como showWarmingOverlay -- vive junto al typing indicator. */}
            {warmingHint && (
              <div className={styles.warmingHint}>
                <AnimatedReveal text={mlT('warmingModel')} />
              </div>
            )}
          </div>
        </div>
      )}

      {bottomContent}

      <div ref={messagesEndRef} aria-hidden="true" />
    </div>
  );
}
