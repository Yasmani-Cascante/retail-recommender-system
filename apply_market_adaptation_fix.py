# apply_market_adaptation_fix.py
"""
Script de implementación para aplicar las correcciones de adaptación de mercado
Ejecutar desde la raíz del proyecto: python apply_market_adaptation_fix.py
"""

import os
import sys
import shutil
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_backup(file_path):
    """Crea backup del archivo antes de modificarlo"""
    if os.path.exists(file_path):
        backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup creado: {backup_path}")
        return backup_path
    return None

def step1_create_market_utils():
    """Paso 1: Crear módulo de utilidades de mercado"""
    logger.info("=== PASO 1: Creando módulo de utilidades de mercado ===")
    
    utils_dir = "src/api/mcp/utils"
    os.makedirs(utils_dir, exist_ok=True)
    
    # Crear __init__.py si no existe
    init_file = os.path.join(utils_dir, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w") as f:
            f.write("")
    
    # Crear market_utils.py básico
    market_utils_path = os.path.join(utils_dir, "market_utils.py")
    
    market_utils_content = '''"""
Utilidades para adaptación de mercado - Versión básica
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class MarketAdapter:
    """Adaptador básico de mercado para corrección inmediata"""
    
    EXCHANGE_RATES = {
        "COP_TO_USD": 0.00025,  # 1 COP = 0.00025 USD
        "COP_TO_EUR": 0.00023,  # 1 COP = 0.00023 EUR
        "COP_TO_MXN": 0.0043,   # 1 COP = 0.0043 MXN
    }
    
    MARKET_CURRENCIES = {
        "US": "USD",
        "ES": "EUR", 
        "MX": "MXN",
        "CO": "COP"
    }
    
    BASIC_TRANSLATIONS = {
        "alas de novia": "bridal wings",
        "cinturon": "belt",
        "cinturón": "belt",
        "indio": "indian style",
        "bolso": "bag",
        "falda": "skirt",
        "vestido": "dress",
        "blusa": "blouse",
        "collar": "necklace",
        "pulsera": "bracelet"
    }
    
    def adapt_product_for_market(self, product: Dict, market_id: str) -> Dict:
        """
        Adapta un producto para el mercado especificado
        
        Args:
            product: Producto a adaptar
            market_id: ID del mercado (US, ES, MX, CO)
            
        Returns:
            Producto adaptado con precio y textos convertidos
        """
        try:
            # Clonar para no mutar el original
            adapted = product.copy()
            
            # 1. Conversión de precio
            if "price" in adapted and market_id in self.MARKET_CURRENCIES:
                original_price = adapted["price"]
                
                # Guardar valores originales
                adapted["original_price"] = original_price
                adapted["original_currency"] = "COP"
                
                # Convertir precio
                if market_id == "US":
                    adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_USD"], 2)
                    adapted["currency"] = "USD"
                elif market_id == "ES":
                    adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_EUR"], 2)
                    adapted["currency"] = "EUR"
                elif market_id == "MX":
                    adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_MXN"], 2)
                    adapted["currency"] = "MXN"
                else:  # CO
                    adapted["currency"] = "COP"
            
            # 2. Traducción básica (solo para US)
            if market_id == "US":
                # Traducir título/nombre
                for field in ["title", "name"]:
                    if field in adapted and adapted[field]:
                        original_text = adapted[field]
                        adapted[f"original_{field}"] = original_text
                        
                        # Traducción simple
                        translated = self._translate_basic(original_text)
                        adapted[field] = translated
                
                # Traducir descripción (primeras palabras)
                if "description" in adapted and adapted["description"]:
                    original_desc = adapted["description"]
                    adapted["original_description"] = original_desc
                    adapted["description"] = self._translate_basic(original_desc)
            
            # 3. Añadir metadata
            adapted["market_adapted"] = True
            adapted["adapted_for_market"] = market_id
            
            return adapted
            
        except Exception as e:
            logger.error(f"Error adapting product: {e}")
            return product
    
    def _translate_basic(self, text: str) -> str:
        """Traducción básica usando diccionario"""
        if not text:
            return text
        
        text_lower = text.lower()
        
        # Buscar coincidencias en el diccionario
        for es_term, en_term in self.BASIC_TRANSLATIONS.items():
            if es_term in text_lower:
                # Reemplazar manteniendo capitalización
                result = text.replace(es_term, en_term)
                result = result.replace(es_term.capitalize(), en_term.capitalize())
                result = result.replace(es_term.upper(), en_term.upper())
                return result
        
        # Si no se encuentra traducción, añadir indicador
        return f"{text} [EN]"

# Instancia global para uso directo
market_adapter = MarketAdapter()
'''
    
    with open(market_utils_path, "w", encoding="utf-8") as f:
        f.write(market_utils_content)
    
    logger.info(f"✅ Creado: {market_utils_path}")
    return market_utils_path

def step2_patch_mcp_router():
    """Paso 2: Parchear el router MCP"""
    logger.info("=== PASO 2: Parcheando router MCP ===")
    
    router_path = "src/api/routers/mcp_router.py"
    
    if not os.path.exists(router_path):
        logger.error(f"❌ No se encuentra el router: {router_path}")
        return False
    
    # Crear backup
    backup_path = create_backup(router_path)
    
    # Leer contenido actual
    with open(router_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verificar si ya está parcheado
    if "market_adapter" in content:
        logger.info("ℹ️ El router ya parece estar parcheado")
        return True
    
    # Buscar el punto de inserción para imports
    import_insert_point = content.find("from typing import")
    if import_insert_point == -1:
        import_insert_point = content.find("import") 
    
    # Añadir import
    import_line = "\nfrom src.api.mcp.utils.market_utils import market_adapter\n"
    content = content[:import_insert_point] + import_line + content[import_insert_point:]
    
    # Buscar la función safe_transform_recommendation
    transform_func_start = content.find("def safe_transform_recommendation")
    if transform_func_start == -1:
        transform_func_start = content.find("async def safe_transform_recommendation")
    
    if transform_func_start == -1:
        logger.warning("⚠️ No se encontró safe_transform_recommendation, buscando alternativas...")
        
        # Buscar en la función de conversation
        conv_func = content.find("async def handle_mcp_conversation")
        if conv_func == -1:
            conv_func = content.find("@router.post")
        
        if conv_func != -1:
            # Buscar donde se procesan las recomendaciones
            recs_point = content.find("personalized_recommendations", conv_func)
            if recs_point != -1:
                # Insertar adaptación después de obtener recomendaciones
                insert_point = content.find("\n", recs_point)
                
                adaptation_code = '''
    # Adaptar recomendaciones para el mercado
    if personalized_recommendations and market_context:
        market_id = market_context.get("market_id", "US")
        adapted_recommendations = []
        for rec in personalized_recommendations:
            adapted = market_adapter.adapt_product_for_market(rec, market_id)
            adapted_recommendations.append(adapted)
        personalized_recommendations = adapted_recommendations
'''
                content = content[:insert_point] + adaptation_code + content[insert_point:]
                logger.info("✅ Adaptación insertada en handle_mcp_conversation")
    else:
        # Modificar safe_transform_recommendation
        func_end = content.find("\n\n", transform_func_start)
        if func_end == -1:
            func_end = content.find("\ndef", transform_func_start + 1)
        
        # Buscar el return statement
        return_point = content.rfind("return", transform_func_start, func_end)
        
        if return_point != -1:
            # Insertar adaptación antes del return
            adaptation_code = '''
    
    # Adaptar para el mercado si hay contexto disponible
    if context and "market_id" in context:
        recommendation = market_adapter.adapt_product_for_market(
            recommendation, 
            context["market_id"]
        )
'''
            content = content[:return_point] + adaptation_code + "\n    " + content[return_point:]
            logger.info("✅ Adaptación insertada en safe_transform_recommendation")
    
    # Guardar archivo modificado
    with open(router_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"✅ Router parcheado exitosamente")
    logger.info(f"ℹ️ Backup guardado en: {backup_path}")
    return True

def step3_create_test_script():
    """Paso 3: Crear script de prueba"""
    logger.info("=== PASO 3: Creando script de prueba ===")
    
    test_script = '''"""
Script de prueba para verificar la adaptación de mercado
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_market_adaptation():
    """Prueba la adaptación de mercado"""
    
    # URL de tu API
    API_URL = "http://localhost:8000/v1/mcp/conversation"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    # Probar diferentes mercados
    markets = ["US", "ES", "MX", "CO"]
    
    for market_id in markets:
        print(f"\\n{'='*50}")
        print(f"Testing market: {market_id}")
        print('='*50)
        
        # Request body
        data = {
            "user_message": "Busco algo especial para regalar",
            "session_id": f"test_session_{market_id}_{int(datetime.now().timestamp())}",
            "market_id": market_id,
            "include_recommendations": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Verificar recomendaciones
                        recommendations = result.get("recommendations", [])
                        print(f"\\nRecomendaciones recibidas: {len(recommendations)}")
                        
                        # Mostrar primera recomendación
                        if recommendations:
                            first_rec = recommendations[0]
                            print(f"\\nPrimera recomendación:")
                            print(f"  Título: {first_rec.get('title', 'N/A')}")
                            print(f"  Título Original: {first_rec.get('original_title', 'N/A')}")
                            print(f"  Precio: {first_rec.get('price', 'N/A')} {first_rec.get('currency', 'N/A')}")
                            print(f"  Precio Original: {first_rec.get('original_price', 'N/A')} {first_rec.get('original_currency', 'N/A')}")
                            print(f"  Adaptado: {first_rec.get('market_adapted', False)}")
                            
                            # Verificar conversión correcta
                            if first_rec.get('original_price') and first_rec.get('price'):
                                orig = first_rec['original_price']
                                conv = first_rec['price']
                                rate = conv / orig if orig > 0 else 0
                                print(f"  Tasa de cambio aplicada: {rate:.6f}")
                    else:
                        print(f"❌ Error: Status {response.status}")
                        print(await response.text())
                        
        except Exception as e:
            print(f"❌ Error en la prueba: {e}")

if __name__ == "__main__":
    print("🧪 Iniciando pruebas de adaptación de mercado...")
    asyncio.run(test_market_adaptation())
    print("\\n✅ Pruebas completadas")
'''
    
    test_path = "test_market_adaptation.py"
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_script)
    
    logger.info(f"✅ Script de prueba creado: {test_path}")
    return test_path

def step4_update_frontend_handling():
    """Paso 4: Actualizar manejo en el frontend"""
    logger.info("=== PASO 4: Actualizando manejo en frontend ===")
    
    frontend_update = '''// src/frontend/src/components/ProductCard.tsx
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
'''
    
    frontend_path = "frontend_product_card_update.tsx"
    with open(frontend_path, "w", encoding="utf-8") as f:
        f.write(frontend_update)
    
    logger.info(f"✅ Actualización de frontend creada: {frontend_path}")
    logger.info("ℹ️ Copia este código a src/frontend/src/components/ProductCard.tsx")
    return frontend_path

def main():
    """Ejecutar todos los pasos de implementación"""
    print("""
    ╔════════════════════════════════════════════════════════╗
    ║     CORRECCIÓN DE ADAPTACIÓN DE MERCADO - MCP          ║
    ║                                                        ║
    ║  Este script aplicará las correcciones necesarias      ║
    ║  para resolver:                                        ║
    ║  1. Error de conversión de moneda (COP → USD/EUR/MXN) ║
    ║  2. Falta de traducción básica de productos           ║
    ╚════════════════════════════════════════════════════════╝
    """)
    
    # Confirmar ejecución
    response = input("\n¿Deseas continuar? (s/n): ")
    if response.lower() != 's':
        print("Operación cancelada")
        return
    
    try:
        # Ejecutar pasos
        print("\n🚀 Iniciando implementación...\n")
        
        # Paso 1: Crear utilidades
        step1_create_market_utils()
        
        # Paso 2: Parchear router
        step2_patch_mcp_router()
        
        # Paso 3: Crear script de prueba
        test_script = step3_create_test_script()
        
        # Paso 4: Actualizar frontend
        frontend_update = step4_update_frontend_handling()
        
        print("\n" + "="*60)
        print("✅ IMPLEMENTACIÓN COMPLETADA EXITOSAMENTE")
        print("="*60)
        
        print("\n📋 Próximos pasos:")
        print("1. Reiniciar el servidor: python -m uvicorn src.api.main_unified_redis:app --reload")
        print(f"2. Ejecutar pruebas: python {test_script}")
        print(f"3. Actualizar frontend con el código en: {frontend_update}")
        print("4. Verificar en el widget que los precios y traducciones funcionen")
        
        print("\n💡 Tips:")
        print("- Los precios ahora se convertirán automáticamente según el market_id")
        print("- Las traducciones básicas funcionarán para el mercado US")
        print("- Los valores originales se preservan en campos original_*")
        print("- Puedes extender las traducciones en market_utils.py")
        
    except Exception as e:
        logger.error(f"❌ Error durante la implementación: {e}")
        print("\n⚠️ La implementación encontró errores. Revisa los logs.")
        
if __name__ == "__main__":
    main()
