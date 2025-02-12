import shopify
from typing import List, Dict
import logging

class ShopifyIntegration:
    def __init__(self, shop_url: str, access_token: str):
        try:
            self.session = shopify.Session(shop_url, '2024-01', access_token)
            shopify.ShopifyResource.activate_session(self.session)
            logging.info(f"Shopify session initialized for shop: {shop_url}")
        except Exception as e:
            logging.error(f"Error initializing Shopify session: {str(e)}")
            raise

    def get_products(self) -> List[Dict]:
        """
        Obtiene todos los productos de Shopify y los formatea para el sistema de recomendaciones
        """
        try:
            products = []
            page = 1
            while True:
                batch = shopify.Product.find(limit=250, page=page)
                if not batch:
                    break

                for p in batch:
                    if not p.variants:  # Skip products without variants
                        continue
                        
                    product_dict = {
                        "id": str(p.id),
                        "name": p.title,
                        "description": p.body_html if p.body_html else "",
                        "price": float(p.variants[0].price) if p.variants[0].price else 0.0,
                        "category": p.product_type if p.product_type else "Unknown",
                        "attributes": {
                            "vendor": p.vendor if p.vendor else "",
                            "tags": p.tags.split(',') if p.tags else [],
                            "variants": [
                                {
                                    "id": str(v.id),
                                    "title": v.title,
                                    "price": float(v.price) if v.price else 0.0,
                                    "sku": v.sku if v.sku else "",
                                    "inventory_quantity": v.inventory_quantity if v.inventory_quantity else 0
                                }
                                for v in p.variants
                            ],
                            "collections": self.get_product_collections(p.id)
                        }
                    }
                    products.append(product_dict)
                
                page += 1
                
            logging.info(f"Retrieved {len(products)} products from Shopify")
            return products
            
        except Exception as e:
            logging.error(f"Error fetching products from Shopify: {str(e)}")
            raise

    def get_product_collections(self, product_id: int) -> List[str]:
        """
        Obtiene las colecciones a las que pertenece un producto
        """
        try:
            collections = shopify.CustomCollection.find(product_id=product_id)
            return [c.title for c in collections] if collections else []
        except Exception as e:
            logging.error(f"Error fetching collections for product {product_id}: {str(e)}")
            return []

    def get_user_events(self, user_id: str) -> List[Dict]:
        """
        Obtiene los eventos de un usuario específico
        Por implementar según necesidades específicas
        """
        # Implementar según los requisitos específicos
        # Podrías usar Orders API, Customer API, etc.
        pass

    def get_orders_by_customer(self, customer_id: str) -> List[Dict]:
        """
        Obtiene los pedidos de un cliente específico
        """
        try:
            orders = shopify.Order.find(customer_id=customer_id)
            return [{
                "id": str(order.id),
                "created_at": order.created_at,
                "products": [
                    {
                        "product_id": str(item.product_id),
                        "variant_id": str(item.variant_id),
                        "quantity": item.quantity
                    }
                    for item in order.line_items
                ]
            } for order in orders]
        except Exception as e:
            logging.error(f"Error fetching orders for customer {customer_id}: {str(e)}")
            return []

    def __del__(self):
        """
        Cierra la sesión de Shopify al destruir la instancia
        """
        try:
            shopify.ShopifyResource.clear_session()
        except:
            pass