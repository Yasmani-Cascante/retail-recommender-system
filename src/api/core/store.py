from src.api.integrations.shopify_client import ShopifyIntegration
from src.api.integrations.shopify_kb_client import ShopifyKBClient  # ✅ NUEVO
import os
import logging

# Variables globales para los clientes
shopify_client = None
shopify_kb_client = None  # ✅ NUEVO

def init_shopify():
    """Initialize basic Shopify client for products."""
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
    else:
        logging.error("Missing Shopify credentials: SHOPIFY_SHOP_URL or SHOPIFY_ACCESS_TOKEN not set")
    return None

def init_shopify_kb_client():  # ✅ NUEVO
    """Initialize Shopify KB client for Knowledge Base pages."""
    global shopify_kb_client
    shop_url = os.getenv("SHOPIFY_SHOP_URL")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    if shop_url and access_token:
        try:
            shopify_kb_client = ShopifyKBClient(
                shop_url=shop_url, 
                access_token=access_token
            )
            logging.info(f"Shopify KB client initialized for {shop_url}")
            return shopify_kb_client
        except Exception as e:
            logging.error(f"Error initializing Shopify KB client: {e}")
    else:
        logging.error("Missing Shopify credentials: SHOPIFY_SHOP_URL or SHOPIFY_ACCESS_TOKEN not set")
    return None

def get_shopify_client():
    """Get Shopify basic client singleton."""
    global shopify_client
    if not shopify_client:
        return init_shopify()
    return shopify_client

def get_shopify_kb_client():  # ✅ NUEVO
    """Get Shopify KB client singleton."""
    global shopify_kb_client
    if not shopify_kb_client:
        return init_shopify_kb_client()
    return shopify_kb_client