# Script de prueba rápido
import asyncio
from src.api.integrations.shopify_kb_client import create_shopify_kb_client
from src.api.core.config import get_settings

async def test_title_translation():
    client = create_shopify_kb_client(
        shop_url=get_settings().SHOPIFY_SHOP_URL,
        access_token=get_settings().SHOPIFY_ACCESS_TOKEN
    )
    
    # Test con página conocida
    title_es = await client.get_page_title_translation(123456789, "es")
    title_en = await client.get_page_title_translation(123456789, "en")
    
    print(f"ES: {title_es}")
    print(f"EN: {title_en}")
    
    # Verificar que son diferentes
    assert title_es != title_en, "Títulos deberían ser diferentes"
    print("✅ Test passed!")

asyncio.run(test_title_translation())