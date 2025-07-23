import type { ProductRecommendation } from '../types/widget';

interface ProductCardProps {
  product: ProductRecommendation;
}

export function ProductCard({ product }: ProductCardProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(price);
  };

  const handleProductClick = () => {
    // TODO: Implement product click tracking
    console.log('Product clicked:', product.id);
    
    // If product has a URL, open it
    if (product.imageUrl) {
      // For now, just log. In production, this would navigate to product page
      console.log('Navigate to product:', product.title);
    }
  };

  return (
    <div 
      className="rr-flex rr-bg-white rr-border rr-border-gray-200 rr-rounded-lg rr-p-3 hover:rr-shadow-md rr-transition-shadow rr-cursor-pointer"
      onClick={handleProductClick}
    >
      {product.imageUrl && (
        <img
          src={product.imageUrl}
          alt={product.title}
          className="rr-w-12 rr-h-12 rr-object-cover rr-rounded-md rr-mr-3 rr-flex-shrink-0"
          onError={(e) => {
            // Hide broken images
            e.currentTarget.style.display = 'none';
          }}
        />
      )}
      
      <div className="rr-flex-1 rr-min-w-0">
        <h4 className="rr-text-sm rr-font-medium rr-text-gray-900 rr-truncate">
          {product.title}
        </h4>
        
        <p className="rr-text-xs rr-text-gray-600 rr-mt-1 rr-line-clamp-2">
          {product.description}
        </p>
        
        <div className="rr-flex rr-items-center rr-justify-between rr-mt-2">
          <span className="rr-text-sm rr-font-semibold rr-text-primary-600">
            {formatPrice(product.price)}
          </span>
          
          {product.category && (
            <span className="rr-text-xs rr-text-gray-500 rr-truncate rr-ml-2">
              {product.category}
            </span>
          )}
        </div>

        {/* Show confidence score if available */}
        {product.score && product.score > 0 && (
          <div className="rr-mt-1">
            <div className="rr-flex rr-items-center">
              <div className="rr-flex-1 rr-bg-gray-200 rr-rounded-full rr-h-1">
                <div 
                  className="rr-bg-primary-600 rr-h-1 rr-rounded-full" 
                  style={{ width: `${Math.round(product.score * 100)}%` }}
                ></div>
              </div>
              <span className="rr-text-xs rr-text-gray-500 rr-ml-2">
                {Math.round(product.score * 100)}% match
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}