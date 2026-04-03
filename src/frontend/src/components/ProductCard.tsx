import type { ProductRecommendation } from '../types/widget';
import styles from './ProductCard.module.css';

interface ProductCardProps {
  product: ProductRecommendation;
}

export function ProductCard({ product }: ProductCardProps) {
  /**
   * formatPrice
   *
   * Uses Intl.NumberFormat for locale-aware currency display.
   * The currency comes from the normalized recommendation — it is always a
   * valid ISO 4217 code (EUR, USD, MXN, CLP) because normalizeRecommendation()
   * in api.ts coerces it. Fallback to EUR if for any reason it's empty.
   *
   * FIX (27/03/2026): currency parameter is now used from product.currency
   * instead of being hardcoded to 'EUR', fixing multi-market display.
   */
  const formatPrice = (price: number, currency = 'EUR') => {
    return new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    }).format(price);
  };

  /**
   * handleClick — navigate to the product page if a URL is available.
   * The url field is optional (backend returns it inconsistently).
   */
  const handleClick = () => {
    if (product.url) {
      window.open(product.url, '_blank', 'noopener noreferrer');
    }
  };

  // FIX (27/03/2026): price arrives as 0 when the backend did not supply it
  // (e.g. in the diversification path).  Showing "0,00 €" is misleading.
  // Hide the price row entirely when price is 0 or absent.
  const hasPrice = product.price > 0;

  // Show the match score only when it is meaningful (> 0) to avoid "0% match"
  const hasScore = product.score > 0;

  return (
    <div
      className={styles.card}
      onClick={handleClick}
      role={product.url ? 'button' : 'article'}
      tabIndex={product.url ? 0 : undefined}
      onKeyDown={e => e.key === 'Enter' && handleClick()}
      aria-label={product.url ? `Ver producto: ${product.title}` : product.title}
    >
      {/* Imagen o placeholder emoji */}
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

      {/* Info */}
      <div className={styles.info}>
        <div className={styles.title}>{product.title}</div>

        {/* FIX (27/03/2026): description is pre-stripped of HTML in api.ts
            via stripHtml(), so rendering it as plain text is safe. */}
        {product.description && (
          <div className={styles.description}>{product.description}</div>
        )}

        <div className={styles.priceRow}>
          {/* FIX (27/03/2026): Only show price when it is > 0.
              currency now comes from the normalized product object. */}
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

      {/* Navigation arrow — only shown when there is a URL to go to */}
      {product.url && (
        <svg
          className={styles.arrow}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
      )}
    </div>
  );
}
