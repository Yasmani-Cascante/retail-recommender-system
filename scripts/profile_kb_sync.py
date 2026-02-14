"""
KB Sync Performance Profiling
==============================

Este script mide DÓNDE se va el tiempo en el sync:
1. Tiempo en Shopify API calls
2. Tiempo en DB operations
3. Tiempo en cache invalidation

Esto nos dirá si el bottleneck es:
- Network I/O (Shopify API) → Aumentar semaphore NO ayuda
- DB I/O → Aumentar semaphore SÍ ayuda

Author: Yasmani Roque
Date: 14 Feb 2026
"""
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env
project_root = Path(__file__).parent.parent.resolve()
env_path = project_root / ".env"
load_dotenv(env_path)

print(f"📁 .env loaded from: {env_path}")
print(f"✅ .env exists: {env_path.exists()}\n")

# Verificar credenciales DESPUÉS de cargar .env
import os
print(f"🔑 SHOPIFY_SHOP_URL: {os.getenv('SHOPIFY_SHOP_URL')}")
print(f"🔑 SHOPIFY_ACCESS_TOKEN: {'***' + os.getenv('SHOPIFY_ACCESS_TOKEN')[-4:] if os.getenv('SHOPIFY_ACCESS_TOKEN') else 'NOT SET'}")
print(f"🔑 KB_SYNC_SEMAPHORE_SIZE: {os.getenv('KB_SYNC_SEMAPHORE_SIZE', '1 (default)')}\n")

from src.api.dependencies import get_kb_sync_service

class PerformanceProfiler:
    """Context manager para medir tiempos."""
    
    def __init__(self, name: str):
        self.name = name
        self.start = None
        self.duration = None
    
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.duration = time.time() - self.start
        print(f"  ⏱️  {self.name}: {self.duration:.3f}s")

async def profile_single_sync():
    """Profile un sync completo con timing detallado."""
    
    print("=" * 70)
    print("KB SYNC PERFORMANCE PROFILING")
    print("=" * 70)
    
    # Get service
    print("\n🔧 Initializing service...")
    sync_service = await get_kb_sync_service()
    
    print(f"✅ Service initialized")
    print(f"   Semaphore size: {sync_service._db_semaphore._value}")
    
    # Medir sync completo
    print("\n🚀 Running FULL SYNC with detailed profiling...\n")
    
    total_start = time.time()
    
    # Step 1: Fetch pages from Shopify
    with PerformanceProfiler("1️⃣  Fetch KB pages from Shopify"):
        kb_pages = await sync_service.shopify.get_kb_pages(validate_metadata=True)
    
    print(f"   📄 Pages fetched: {len(kb_pages)}")
    
    if not kb_pages:
        print("\n⚠️  No KB pages found - cannot profile")
        return
    
    # Step 2: Profile first page in detail
    print(f"\n🔬 Profiling FIRST PAGE in detail:")
    page, metafields = kb_pages[0]
    print(f"   Page ID: {page.id}")
    print(f"   Title: {page.title}\n")
    
    # 2a: Extract metadata
    with PerformanceProfiler("2️⃣  Extract metadata"):
        kb_metadata = metafields.get("custom.kb_metadata", {})
        sub_intent = kb_metadata.get("sub_intent")
        category = kb_metadata.get("category")
        default_language = kb_metadata.get("language", "es")
    
    # 2b: HTML to Markdown
    with PerformanceProfiler("3️⃣  Convert HTML to Markdown"):
        markdown_content = sync_service._html_to_markdown(page.body_html or "")
    
    # 2c: DB upsert (default language)
    with PerformanceProfiler("4️⃣  DB upsert (default language)"):
        await sync_service._upsert_kb_content(
            sub_intent=sub_intent,
            language=default_language,
            category=category,
            content=markdown_content,
            content_html=page.body_html,
            title=page.title,
            shopify_page_id=page.id,
            shopify_url=f"https://{sync_service.shopify.shop_url}/pages/{page.handle}",
            shopify_handle=page.handle
        )
    
    # 2d: Cache invalidation
    with PerformanceProfiler("5️⃣  Cache invalidation"):
        await sync_service._invalidate_cache(sub_intent, default_language, category)
    
    # 2e: Fetch translations (THIS IS THE EXPENSIVE PART)
    with PerformanceProfiler("6️⃣  Fetch translations from Shopify"):
        translations = await sync_service.shopify.get_page_translations(page.id)
    
    print(f"   📝 Translations found: {len(translations)}")
    
    # 2f: Sync translations
    if translations:
        translation_time = 0
        for locale, translated_html in translations.items():
            if locale == default_language:
                continue
            
            t_start = time.time()
            
            # Fetch translated title
            translated_title = await sync_service.shopify.get_page_title_translation(page.id, locale)
            final_title = translated_title if translated_title else page.title
            
            # Convert HTML
            translated_markdown = sync_service._html_to_markdown(translated_html)
            
            # DB upsert
            await sync_service._upsert_kb_content(
                sub_intent=sub_intent,
                language=locale,
                category=category,
                content=translated_markdown,
                content_html=translated_html,
                title=final_title,
                shopify_page_id=page.id,
                shopify_url=f"https://{sync_service.shopify.shop_url}/pages/{page.handle}",
                shopify_handle=page.handle
            )
            
            # Cache invalidation
            await sync_service._invalidate_cache(sub_intent, locale, category)
            
            translation_time += (time.time() - t_start)
        
        print(f"  ⏱️  7️⃣  Sync all translations: {translation_time:.3f}s")
    
    total_duration = time.time() - total_start
    
    print(f"\n{'=' * 70}")
    print(f"TOTAL TIME (1 page): {total_duration:.3f}s")
    print(f"{'=' * 70}")
    
    # Ahora sync completo para comparar
    print(f"\n🏁 Running FULL SYNC (all {len(kb_pages)} pages)...\n")
    
    full_start = time.time()
    report = await sync_service.sync_all_pages()
    full_duration = time.time() - full_start
    
    print(f"\n{'=' * 70}")
    print(f"FULL SYNC RESULTS:")
    print(f"{'=' * 70}")
    print(f"Total pages: {report.total_pages}")
    print(f"Successful: {report.successful}")
    print(f"Duration: {full_duration:.2f}s")
    print(f"Throughput: {report.total_pages / full_duration:.2f} pages/sec")
    print(f"{'=' * 70}")
    
    # Calcular breakdown
    print(f"\n📊 PERFORMANCE BREAKDOWN (estimated):")
    
    # Extraer tiempos del profiling de 1 página
    # (estos son aproximados basados en lo que vimos arriba)
    print(f"\nPer page (average):")
    avg_per_page = full_duration / report.total_pages if report.total_pages > 0 else 0
    print(f"  Total: {avg_per_page:.3f}s")
    
    print(f"\n🎯 BOTTLENECK ANALYSIS:")
    print(f"   If 'Fetch translations' is the slowest step:")
    print(f"   → Bottleneck is NETWORK I/O (Shopify API)")
    print(f"   → Increasing semaphore WON'T help much")
    print(f"   → Need to optimize API calls or add caching")
    print(f"\n   If 'DB upsert' is the slowest step:")
    print(f"   → Bottleneck is DATABASE I/O")
    print(f"   → Increasing semaphore WILL help")
    print(f"   → M1 optimization is correct approach")
    
    return report

if __name__ == "__main__":
    try:
        result = asyncio.run(profile_single_sync())
        print("\n✅ Profiling completed!")
        
    except Exception as e:
        print(f"\n❌ Profiling failed: {e}")
        import traceback
        traceback.print_exc()