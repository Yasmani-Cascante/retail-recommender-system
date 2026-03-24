import type { ProductRecommendation } from '../types/widget';
import styles from './ProductCard.module.css';

interface ProductCardProps {
  product: ProductRecommendation;
}

export function ProductCard({ product }: ProductCardProps) {
  const formatPrice = (price: number, currency = 'EUR') => {
    return new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    }).format(price);
  };

  const handleClick = () => {
    const url = (product as any).url;
    if (url) window.open(url, '_blank', 'noopener noreferrer');
  };

  return (
    <div
      className={styles.card}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && handleClick()}
      aria-label={`Ver producto: ${product.title}`}
    >
      {/* Imagen o placeholder emoji */}
      <div className={styles.imageBox}>
        {product.imageUrl ? (
          <img
            src={product.imageUrl}
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

        {product.description && (
          <div className={styles.description}>{product.description}</div>
        )}

        <div className={styles.priceRow}>
          <span className={styles.price}>
            {formatPrice(product.price, product.currency || 'EUR')}
          </span>

          {product.score && product.score > 0 && (
            <span className={styles.score}>
              {Math.round(product.score * 100)}% match
            </span>
          )}
        </div>
      </div>

      {/* Flecha de navegación */}
      <svg
        className={styles.arrow}
        width="14" height="14" viewBox="0 0 24 24"
        fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="m9 18 6-6-6-6"/>
      </svg>
    </div>
  );
}
