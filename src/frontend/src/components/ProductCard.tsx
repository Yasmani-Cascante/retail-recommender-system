import React from 'react';
import type { ProductRecommendation } from '../types/widget';
// import styles from './ProductCard.module.css';
import styles from './ProductCard_V.module.css';

// ── Tooltips multilingüe para la barra de acciones (15/06/2026) ──────────────
// navigator.language detecta el idioma real del navegador del usuario.
// Así el tooltip hover refleja el idioma correcto en mercado CH (FR/DE/IT).
const _ACTION_TOOLTIPS: Record<string, {
  showSimilar: string;
  chatAbout: string;
  addToCart: string;
  comingSoon: string;
}> = {
  es: { showSimilar: 'Ver productos similares',      chatAbout: 'Hablar sobre este producto',    addToCart: 'Añadir al carrito',    comingSoon: 'próximamente'   },
  fr: { showSimilar: 'Voir des produits similaires', chatAbout: 'Parler de ce produit',          addToCart: 'Ajouter au panier',   comingSoon: 'prochainement'  },
  de: { showSimilar: 'Ähnliche Produkte',            chatAbout: 'Über dieses Produkt sprechen',  addToCart: 'In den Warenkorb',    comingSoon: 'demnächst'      },
  it: { showSimilar: 'Vedi prodotti simili',         chatAbout: 'Parla di questo prodotto',      addToCart: 'Aggiungi al carrello', comingSoon: 'prossimamente'  },
  en: { showSimilar: 'Show similar products',        chatAbout: 'Chat about this item',          addToCart: 'Add to cart',          comingSoon: 'coming soon'    },
};
// Resolved once at module load — navigator is always available in the browser.
const _navLang = (typeof navigator !== 'undefined' ? navigator.language : 'es')
  .split('-')[0].toLowerCase();
const _T = _ACTION_TOOLTIPS[_navLang] ?? _ACTION_TOOLTIPS['es'];

interface ProductCardProps {
  product: ProductRecommendation;
  /**
   * onChatAbout — "Let's chat about this item" (Sabor 3).
   * Activa el chip de contexto en el input sin enviar mensaje.
   * El usuario escribe su propia pregunta sobre este producto.
   */
  onChatAbout?: (product: ProductRecommendation) => void;
  /**
   * onShowSimilar — "Show me similar items" (Sabor 2).
   * Envía automáticamente una petición de recomendaciones similares
   * a este producto, sin que el usuario tenga que escribir nada.
   */
  onShowSimilar?: (product: ProductRecommendation) => void;
  /**
   * variant — jerarquia visual de la tarjeta (15/10/2026).
   *
   *   'default' — bloque PRINCIPAL: lo que el usuario pidio.
   *   'compact' — bloque de ALTERNATIVAS: mas estrecha, con la imagen algo
   *               atenuada y sin descripcion.
   *
   * POR QUE: con los dos bloques ya separados por titulo, las tarjetas seguian
   * siendo identicas, asi que el peso visual decia "todo esto es lo mismo"
   * mientras el titulo decia lo contrario. Cuando forma y texto se contradicen,
   * gana la forma. La tarjeta compacta alinea las dos senales.
   *
   * No se recorta informacion util: titulo y precio se mantienen. Solo se quita
   * la descripcion, que en este bloque es ruido.
   */
  variant?: 'default' | 'compact';
  /**
   * showDescription — extracto del producto (17/10/2026).
   *
   * Solo en modo EXPANDIDO / MAXIMIZADO. En el chat contraido la tarjeta vive
   * en un carrusel estrecho y el extracto, aun recortado a 2 lineas, apreta
   * demasiado el conjunto: esa fue la razon de quitarlo el 10/04/2026 y sigue
   * siendo cierta ahi. Con el chat expandido hay sitio de sobra, y entonces el
   * extracto ayuda a decidir sin salir de la conversacion.
   *
   * Se controla por PROP y no por CSS a proposito: el estado expandido vive en
   * MessageList.module.css y la descripcion en ProductCard_V.module.css. Con
   * CSS Modules cada archivo tiene su propio hash, asi que un selector
   * descendente entre ambos no casaria -- fallaria en silencio, que es justo
   * el modo de fallo que ya nos costo dos ciclos esta semana.
   */
  showDescription?: boolean;
}

export function ProductCard({ product, onChatAbout, onShowSimilar, variant = 'default', showDescription = false }: ProductCardProps) {
  /**
   * formatPrice — locale-aware currency display.
   * Currency comes from the normalized recommendation (always a valid ISO 4217
   * code). Fallback to EUR if empty.
   */
  const formatPrice = (price: number, currency = 'EUR') => {
    return new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    }).format(price);
  };

  /**
   * handleCardClick — navega a la página del producto al hacer click en la
   * tarjeta completa. La flecha de navegación ha sido eliminada; ahora toda
   * la tarjeta es clickable para ir al producto.
   * Los botones de la barra inferior tienen stopPropagation para no activar
   * esta navegación al mismo tiempo que su propia acción.
   */
  const handleCardClick = () => {
    if (product.url) {
      window.open(product.url, '_blank', 'noopener noreferrer');
    }
  };

  /**
   * handleChatAbout — activa el chip de contexto en el input.
   * stopPropagation evita la navegación al producto.
   */
  const handleChatAbout = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChatAbout?.(product);
  };

  /**
   * handleShowSimilar — envía petición automática de similares.
   * stopPropagation evita la navegación al producto.
   */
  const handleShowSimilar = (e: React.MouseEvent) => {
    e.stopPropagation();
    onShowSimilar?.(product);
  };

  const hasPrice = product.price > 0;

  // FASE 4 (13/10/2026) — el "% match" solo donde hay una medida REAL.
  //
  // Hasta hoy se usaba `product.score`, que NO mide parecido: el backend lo
  // genera como score_start menos 0.02 por posicion en la lista. Verificado
  // contra pantalla el 07/10: los porcentajes eran 100, 98, 96, 94, 92, 87,
  // 85, 83 -- exactamente esa escalera. Un producto traido del catalogo por
  // categoria, sin ninguna vecindad visual medida, lucia un "87% match" igual
  // de convincente que uno realmente parecido.
  //
  // `visualScore` SI es la similitud coseno real que calcula FAISS, y llega
  // solo para origin === 'visual'. Se distingue null de 0 a proposito: null
  // es "no hay medida" y 0 seria "medido y pesimo".
  //
  // Regla: sin medida, no se muestra porcentaje. Preferimos no decir nada a
  // decir un numero inventado.
  const measuredScore =
    typeof product.visualScore === 'number' && isFinite(product.visualScore)
      ? product.visualScore
      : null;
  const hasScore = measuredScore !== null && measuredScore > 0;

  // Mostrar la barra de botones solo cuando al menos uno de los callbacks está disponible
  const showActionBar = Boolean(onChatAbout || onShowSimilar);

  return (
    <div
      className={`${styles.card} ${showActionBar ? styles.cardWithActions : ''} ${variant === 'compact' ? styles.cardCompact : ''}`}
      onClick={handleCardClick}
      role={product.url ? 'button' : 'article'}
      tabIndex={product.url ? 0 : undefined}
      onKeyDown={e => e.key === 'Enter' && handleCardClick()}
      aria-label={product.url ? `Ver producto: ${product.title}` : product.title}
    >
      {/* ── Cuerpo principal: imagen + info ── */}
      <div className={styles.cardBody}>
        {/* Imagen o placeholder */}
        <div className={styles.imageBox}>
          {product.image_url ? (
            <img
              src={product.image_url}
              alt={product.title}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
              }}
            />
          ) : (
            '🛍️'
          )}
        </div>

              {/* ── Barra de acciones — patrón Zalando ──────────────────────
          Tres botones debajo del contenido principal.
          Separados visualmente del cuerpo por un borde superior sutil.
          stopPropagation en cada uno para no activar handleCardClick.   */}
      {showActionBar && (
        <div className={styles.actionBar} onClick={e => e.stopPropagation()}>

          {/* Botón Add to basket — deshabilitado, se implementará más adelante */}
          <button
            className={`${styles.actionBtn} ${styles.actionBtnDisabled}`}
            disabled
            aria-label={`${_T.addToCart} (${_T.comingSoon})`}
            title={_T.addToCart}
          >
            {/* Icono bolsa de compras */}
            <svg viewBox="0 0 24 24" width="20" fill="currentColor" strokeWidth="0.1" aria-hidden="true">
              <path d="M21.193 8.712a2.984 2.984 0 0 0-2.986-2.726h-.952v-.751a5.255 5.255 0 0 0-10.51 0v.75h-.951a2.983 2.983 0 0 0-2.986 2.727L1.715 20.73q-.012.135-.012.27A3 3 0 0 0 4.7 24h.005l14.599-.026q.133 0 .265-.012a3 3 0 0 0 2.715-3.258zM8.246 5.235a3.754 3.754 0 0 1 7.508 0v.75H8.246zm11.056 17.238-14.599.025h-.002q-.067 0-.135-.006a1.496 1.496 0 0 1-1.355-1.625l1.093-12.02a1.49 1.49 0 0 1 1.49-1.36h.95V9.74a.75.75 0 0 0 1.502 0V7.487h7.508V9.74c0 .415.336.75.75.75h.002a.75.75 0 0 0 .75-.75V7.487h.951a1.49 1.49 0 0 1 1.49 1.361l1.092 11.993q.006.067.007.133a1.496 1.496 0 0 1-1.494 1.499"></path>
            </svg>
          </button>
          
          {/* Botón Show me similar items — Sabor 2, envío automático */}
          {onShowSimilar && (
            <button
              // className={`${styles.actionBtn} ${styles.actionBtnSimilar}`}
              className={`${styles.actionBtn} ${styles.actionBtnChat}`}
              onClick={handleShowSimilar}
              aria-label={`${_T.showSimilar}: ${product.title}`}
              title={_T.showSimilar}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="20" fill="currentColor" stroke="currentColor"  strokeWidth="0.1" aria-hidden="true">
                <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"/>
              </svg>
            </button>
          )}

          {/* Botón Let's chat about this item — Sabor 3, activa chip */}
          {onChatAbout && (
            <button
              className={`${styles.actionBtn} ${styles.actionBtnChat}`}
              onClick={handleChatAbout}
              aria-label={`${_T.chatAbout}: ${product.title}`}
              title={_T.chatAbout}
            >
              {/* Icono burbuja de chat */}
              <svg viewBox="0 0 24 24" width="21" fill="currentColor" aria-hidden="true"
                xmlns="http://www.w3.org/2000/svg" stroke="currentColor" strokeWidth="0.01">
                  <path d="M16 2H4a3 3 0 00-3 3v8a3 3 0 003 3h1v2.14a.8.8 0 001.188.7L11.3 16H16a3 3 0 003-3V5a3 3 0 00-3-3ZM4 4h12a1 1 0 011 1v8a1 1 0 01-1 1h-5.218l-.452.252L7 16.1V14H4a1 1 0 01-1-1V5a1 1 0 011-1Zm17 2.174A3 3 0 0123 9v8a3 3 0 01-2.846 2.996L20 20v2.14a.8.8 0 01-1.189.7L13.701 20H8.216l3.6-2h2.402l.453.252L18 20.101V18.05l1.95-.05.113-.003A1 1 0 0021 17V6.174Z"></path>
                </svg>
            </button>
          )}

        </div>
      )}

        {/* Info del producto */}
        <div className={styles.info}>
          {/* Vendor / Marca — se muestra encima del título si existe.
              Patrón estándar de e-commerce: marca pequeña + gris arriba,
              título destacado abajo. Si el producto no tiene vendor,
              el elemento no se renderiza (sin espacio residual). */}
          {product.vendor && (
            <div className={styles.vendor}>{product.vendor}</div>
          )}

          <div className={styles.title}>{product.title}</div>

          {/* DESCRIPCION (16/10/2026) -- reactivada SOLO en el bloque principal.

              Historia: se elimino el 10/04/2026 con tres razones validas en su
              momento: (a) el espacio del widget es limitado, (b) la descripcion
              ya aparece al abrir el producto, (c) vendor + titulo + precio
              bastaban para identificar el item.

              Que cambio: desde el 15/10 hay DOS bloques con jerarquia distinta
              (lo pedido / alternativas). La razon (c) seguia siendo cierta para
              IDENTIFICAR, pero el bloque principal ya no solo identifica: es la
              respuesta a lo que el usuario pidio, y ahi un extracto ayuda a
              decidir sin salir del chat. En las alternativas la razon original
              sigue en pie, y por eso la variante compacta la oculta por CSS.

              La razon (a) se respeta con el recorte a 2 lineas de
              `.description` (-webkit-line-clamp: 2): el extracto nunca empuja
              el precio fuera de la tarjeta.

              Nota: durante meses esto no se habria visto aunque se
              descomentara, porque `description` llegaba SIEMPRE vacia -- el
              saneador del router la buscaba en la raiz del item y vive dentro
              de `product_data`. Corregido el 16/10/2026. */}
              
          {showDescription && product.description && (
            <div className={styles.description}>{product.description}</div>
          )}

          <div className={styles.priceRow}>
            {hasPrice && (
              <span className={styles.price}>
                {formatPrice(product.price, product.currency || 'EUR')}
              </span>
            )}
            {hasScore && (
              <span className={styles.score}>
                {Math.round((measuredScore as number) * 100)}% match
              </span>
            )}
          </div>
        </div>
      </div>


    </div>
  );
}
