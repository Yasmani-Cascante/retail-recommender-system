import requests
from typing import List, Dict
import logging
from base64 import b64encode

class ShopifyIntegration:
    def __init__(self, shop_url: str, access_token: str):
        self.shop_url = shop_url.rstrip('/').replace('https://', '').replace('http://', '')
        self.access_token = access_token
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }
        self.api_url = f"https://{self.shop_url}/admin/api/2024-01"
        logging.info(f"Initializing Shopify client with:")
        logging.info(f"Shop URL: {self.shop_url}")
        logging.info(f"API URL: {self.api_url}")
        logging.info(f"Access Token: {self.access_token[:4]}...")

    def get_products(self) -> List[Dict]:
        try:
            url = f"{self.api_url}/products.json"
            logging.info(f"Fetching products from: {url}")
            logging.info(f"Using headers: {self.headers}")
            
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            products = response.json().get('products', [])
            return products
        except Exception as e:
            logging.error(f"Error fetching products: {str(e)}")
            return []

    def get_orders_by_customer(self, customer_id: str) -> List[Dict]:
        try:
            url = f"{self.api_url}/orders.json?customer_id={customer_id}&status=any"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            orders = response.json().get('orders', [])
            return orders
        except Exception as e:
            logging.error(f"Error fetching orders for customer {customer_id}: {str(e)}")
            return []

    def get_customers(self) -> List[Dict]:
        """
        Obtiene la lista de clientes de la tienda
        """
        try:
            url = f"{self.api_url}/customers.json"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            customers = response.json().get('customers', [])
            return customers
        except Exception as e:
            logging.error(f"Error fetching customers: {str(e)}")
            return []