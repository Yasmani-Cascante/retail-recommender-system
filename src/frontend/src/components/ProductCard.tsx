import React from 'react';
import type { ProductRecommendation } from '../types/widget';
import styles from './ProductCard.module.css';
// import styles from './ProductCard_V.module.css';

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
}

export function ProductCard({ product, onChatAbout, onShowSimilar }: ProductCardProps) {
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
  const hasScore = product.score > 0;

  // Mostrar la barra de botones solo cuando al menos uno de los callbacks está disponible
  const showActionBar = Boolean(onChatAbout || onShowSimilar);

  return (
    <div
      className={`${styles.card} ${showActionBar ? styles.cardWithActions : ''}`}
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

          {/* CAMBIO (10/04/2026): descripción eliminada de la carta.
              Razones: (a) el espacio es limitado en el widget,
              (b) la descripción ya aparece al hacer click en el producto,
              (c) la vendor + título + precio son suficientes para identificar el item.
          {product.description && (
            <div className={styles.description}>{product.description}</div>
          )}
          */}

          <div className={styles.priceRow}>
            {hasPrice && (
              <span className={styles.price}>
                {formatPrice(product.price, product.currency || 'EUR')}
              </span>
            )}
            {hasScore && (
              <span className={styles.score}>
                {Math.round(product.score * 100)}% match
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Barra de acciones — patrón Zalando ──────────────────────
          Tres botones debajo del contenido principal.
          Separados visualmente del cuerpo por un borde superior sutil.
          stopPropagation en cada uno para no activar handleCardClick.   */}
      {showActionBar && (
        <div className={styles.actionBar} onClick={e => e.stopPropagation()}>
          
          {/* Botón Show me similar items — Sabor 2, envío automático */}
          {onShowSimilar && (
            <button
              // className={`${styles.actionBtn} ${styles.actionBtnSimilar}`}
              className={`${styles.actionBtn} ${styles.actionBtnChat}`}
              onClick={handleShowSimilar}
              aria-label={`Ver productos similares a ${product.title}`}
              title="Ver productos similares"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="17" fill="currentColor" stroke="currentColor"  strokeWidth="0.1" aria-hidden="true">
                <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"/>
              </svg>
            </button>
          )}

          {/* Botón Let's chat about this item — Sabor 3, activa chip */}
          {onChatAbout && (
            <button
              className={`${styles.actionBtn} ${styles.actionBtnChat}`}
              onClick={handleChatAbout}
              aria-label={`Hablar sobre ${product.title}`}
              title="Hablar sobre este producto"
            >
              {/* Icono burbuja de chat */}
              <svg height="24" viewBox="0 0 24 24" width="18" fill="currentColor" aria-hidden="true"
                xmlns="http://www.w3.org/2000/svg" stroke="currentColor" strokeWidth="0.01">
                  <path d="M16 2H4a3 3 0 00-3 3v8a3 3 0 003 3h1v2.14a.8.8 0 001.188.7L11.3 16H16a3 3 0 003-3V5a3 3 0 00-3-3ZM4 4h12a1 1 0 011 1v8a1 1 0 01-1 1h-5.218l-.452.252L7 16.1V14H4a1 1 0 01-1-1V5a1 1 0 011-1Zm17 2.174A3 3 0 0123 9v8a3 3 0 01-2.846 2.996L20 20v2.14a.8.8 0 01-1.189.7L13.701 20H8.216l3.6-2h2.402l.453.252L18 20.101V18.05l1.95-.05.113-.003A1 1 0 0021 17V6.174Z"></path>
                </svg>
            </button>
          )}

          {/* Botón Add to basket — deshabilitado, se implementará más adelante */}
          <button
            className={`${styles.actionBtn} ${styles.actionBtnDisabled}`}
            disabled
            aria-label="Añadir al carrito (próximamente)"
            title="Anadir al carrito"
          >
            {/* Icono bolsa de compras */}
            <svg viewBox="0 0 24 24" width="18" stroke="currentColor" strokeWidth="0.1" aria-hidden="true">
              <path d="M21.193 8.712a2.984 2.984 0 0 0-2.986-2.726h-.952v-.751a5.255 5.255 0 0 0-10.51 0v.75h-.951a2.983 2.983 0 0 0-2.986 2.727L1.715 20.73q-.012.135-.012.27A3 3 0 0 0 4.7 24h.005l14.599-.026q.133 0 .265-.012a3 3 0 0 0 2.715-3.258zM8.246 5.235a3.754 3.754 0 0 1 7.508 0v.75H8.246zm11.056 17.238-14.599.025h-.002q-.067 0-.135-.006a1.496 1.496 0 0 1-1.355-1.625l1.093-12.02a1.49 1.49 0 0 1 1.49-1.36h.95V9.74a.75.75 0 0 0 1.502 0V7.487h7.508V9.74c0 .415.336.75.75.75h.002a.75.75 0 0 0 .75-.75V7.487h.951a1.49 1.49 0 0 1 1.49 1.361l1.092 11.993q.006.067.007.133a1.496 1.496 0 0 1-1.494 1.499"></path>
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
