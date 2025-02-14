import requests
from typing import List, Dict
import logging

class ShopifyIntegration:
    def __init__(self, shop_url: str, access_token: str):
        self.shop_url = shop_url.rstrip('/').replace('https://', '').replace('http://', '')
        self.access_token = access_token
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }
        self.api_url = f"https://{self.shop_url}/admin/api/2024-01"

    def get_products(self) -> List[Dict]:
        try:
            products = []
            url = f"{self.api_url}/products.json"
            
            while url:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                for p in data['products']:
                    if not p.get('variants'):
                        continue
                        
                    product_dict = {
                        "id": str(p['id']),
                        "name": p['title'],
                        "description": p.get('body_html', ''),
                        "price": float(p['variants'][0]['price']) if p['variants'] else 0.0,
                        "category": p.get('product_type', 'Unknown'),
                        "attributes": {
                            "vendor": p.get('vendor', ''),
                            "tags": p.get('tags', '').split(',') if p.get('tags') else [],
                            "variants": [
                                {
                                    "id": str(v['id']),
                                    "title": v['title'],
                                    "price": float(v['price']) if v.get('price') else 0.0,
                                    "sku": v.get('sku', ''),
                                    "inventory_quantity": v.get('inventory_quantity', 0)
                                }
                                for v in p['variants']
                            ]
                        }
                    }
                    
                    # Obtener colecciones directamente del producto si están disponibles
                    collections = []
                    if p.get('collections'):
                        collections = [c['title'] for c in p['collections']]
                    product_dict['attributes']['collections'] = collections
                    
                    products.append(product_dict)
                
                # Check for pagination
                link_header = response.headers.get('Link', '')
                url = None
                if 'rel="next"' in link_header:
                    url = link_header.split('; rel="next"')[0].strip('<>')
                
            logging.info(f"Retrieved {len(products)} products from Shopify")
            return products
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching products from Shopify: {str(e)}")
            raise

    def get_orders_by_customer(self, customer_id: str) -> List[Dict]:
        try:
            url = f"{self.api_url}/orders.json?customer_id={customer_id}&status=any"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            orders = response.json().get('orders', [])
            
            return [{
                "id": str(order['id']),
                "created_at": order['created_at'],
                "products": [
                    {
                        "product_id": str(item.get('product_id')),
                        "variant_id": str(item.get('variant_id')),
                        "quantity": item.get('quantity', 0)
                    }
                    for item in order.get('line_items', [])
                ]
            } for order in orders]
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching orders for customer {customer_id}: {str(e)}")
            return []