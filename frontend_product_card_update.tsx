// src/frontend/src/components/ProductCard.tsx
// Actualización para manejar precios adaptados

import React from 'react';

interface ProductCardProps {
  product: {
    id: string;
    title: string;
    original_title?: string;
    description?: string;
    price: number;
    original_price?: number;
    currency: string;
    original_currency?: string;
    image?: string;
    score?: number;
    market_adapted?: boolean;
  };
}

export const ProductCard: React.FC<ProductCardProps> = ({ product }) => {
  // Formatear precio según moneda
  const formatPrice = (price: number, currency: string): string => {
    const formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    
    return formatter.format(price);
  };
  
  // Mostrar precio original si existe y es diferente
  const showOriginalPrice = product.original_price && 
                           product.original_price !== product.price;
  
  return (
    <div className="bg-white rounded-lg shadow-md p-4 hover:shadow-lg transition-shadow">
      {product.image && (
        <img 
          src={product.image} 
          alt={product.title}
          className="w-full h-48 object-cover rounded-md mb-3"
        />
      )}
      
      <h3 className="font-semibold text-lg mb-1">
        {product.title}
      </h3>
      
      {product.original_title && product.original_title !== product.title && (
        <p className="text-sm text-gray-500 mb-2">
          {product.original_title}
        </p>
      )}
      
      {product.description && (
        <p className="text-gray-600 text-sm mb-3 line-clamp-2">
          {product.description}
        </p>
      )}
      
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xl font-bold text-blue-600">
            {formatPrice(product.price, product.currency)}
          </p>
          
          {showOriginalPrice && (
            <p className="text-sm text-gray-500 line-through">
              {formatPrice(product.original_price!, product.original_currency || 'COP')}
            </p>
          )}
        </div>
        
        {product.score && (
          <div className="text-sm text-gray-600">
            Score: {(product.score * 100).toFixed(0)}%
          </div>
        )}
      </div>
      
      {product.market_adapted && (
        <div className="mt-2 text-xs text-green-600">
          ✓ Adapted for your market
        </div>
      )}
    </div>
  );
};
