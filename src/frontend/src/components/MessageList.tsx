import { useEffect, useRef, useState } from 'react';
import type { Message } from '../types/widget';
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
}

export function MessageList({ messages, isLoading, onChatAbout, onShowSimilar }: MessageListProps) {
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
                  {/* Imagen circular del producto ("Ver similares" / "Preguntar") */}
                  {message.suggestionChip.image_url && (
                    <img
                      src={message.suggestionChip.image_url}
                      alt=""
                      className={styles.suggestionChipImg}
                      aria-hidden="true"
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  )}
                  <h4>{message.suggestionChip.label}</h4>
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
              className={`${styles.bubble} ${
                message.type === 'user'
                  ? styles.bubbleUser
                  : message.type === 'error'
                  ? styles.bubbleError
                  : styles.bubbleAssistant
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
              <div>
                <span className={styles.recoLabel}>Recomendado para ti</span>
                  <div className={styles.productsList}>
                    {message.recommendations.slice(0, 3).map((product) => (
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
