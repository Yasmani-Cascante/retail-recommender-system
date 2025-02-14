from src.api.integrations.shopify_client import ShopifyIntegration
import os
import logging

# Variable global para el cliente
shopify_client = None

def init_shopify():
    global shopify_client
    shop_url = os.getenv("SHOPIFY_SHOP_URL")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    if shop_url and access_token:
        try:
            shopify_client = ShopifyIntegration(shop_url=shop_url, access_token=access_token)
            logging.info(f"Shopify client initialized for {shop_url}")
            return shopify_client
        except Exception as e:
            logging.error(f"Error initializing Shopify client: {e}")
    return None

def get_shopify_client():
    global shopify_client
    if not shopify_client:
        return init_shopify()
    return shopify_client