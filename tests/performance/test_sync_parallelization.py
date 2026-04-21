"""
Performance Test: Sync Parallelization Validation
==================================================

This script validates that the KB sync parallelization is working correctly
and measures the actual performance improvement.

What we're testing:
1. Sequential sync time baseline (if we had sequential code)
2. Parallel sync time actual (current implementation)
3. Performance improvement percentage
4. Verify all pages are synced correctly

Expected Results:
- 6 pages sequential: ~2.4s (400ms per metafields fetch)
- 6 pages parallel: ~500-800ms (single API call wave)
- Improvement: 60-70%

Author: Retail Recommender System Team
Date: 2026-01-19
"""

import asyncio
import time
import asyncpg
from redis import Redis
from typing import List, Tuple
from datetime import datetime

from src.api.core.config import settings
from src.api.integrations.shopify_kb_client import ShopifyKBClient
from src.api.services.shopify_kb_sync import ShopifyKBSyncService
from src.api.core.models.kb_models import ShopifyPage


# ══════════════════════════════════════════════════════════════════════════
# BENCHMARK: SEQUENTIAL METAFIELDS FETCH (SIMULATED)
# ══════════════════════════════════════════════════════════════════════════

async def benchmark_sequential_metafields(
    client: ShopifyKBClient,
    pages: List[ShopifyPage]
) -> Tuple[float, List]:
    """
    Simulate sequential metafields fetching (for baseline comparison).
    
    This is what the OLD code would have done (fetch one by one).
    
    Args:
        client: ShopifyKBClient instance
        pages: List of ShopifyPage objects
        
    Returns:
        (duration_seconds, metafields_list)
    """
    print("\n" + "=" * 70)
    print("BENCHMARK: Sequential Metafields Fetch (BASELINE)")
    print("=" * 70)
    
    start_time = time.time()
    metafields_list = []
    
    for i, page in enumerate(pages, 1):
        print(f"[{i}/{len(pages)}] Fetching metafields for page {page.id}...", end=" ")
        
        page_start = time.time()
        metafields = await client.get_page_metafields(page.id)
        page_duration = time.time() - page_start
        
        metafields_list.append(metafields)
        print(f"✓ ({page_duration * 1000:.0f}ms)")
    
    total_duration = time.time() - start_time
    
    print(f"\n✅ Sequential Total: {total_duration:.2f}s")
    print(f"   Average per page: {(total_duration / len(pages)) * 1000:.0f}ms")
    
    return total_duration, metafields_list


# ══════════════════════════════════════════════════════════════════════════
# BENCHMARK: PARALLEL METAFIELDS FETCH (CURRENT IMPLEMENTATION)
# ══════════════════════════════════════════════════════════════════════════

async def benchmark_parallel_metafields(
    client: ShopifyKBClient,
    pages: List[ShopifyPage]
) -> Tuple[float, List]:
    """
    Benchmark parallel metafields fetching (current implementation).
    
    This is what the NEW code does (fetch all in parallel with asyncio.gather).
    
    Args:
        client: ShopifyKBClient instance
        pages: List of ShopifyPage objects
        
    Returns:
        (duration_seconds, metafields_list)
    """
    print("\n" + "=" * 70)
    print("BENCHMARK: Parallel Metafields Fetch (OPTIMIZED)")
    print("=" * 70)
    
    start_time = time.time()
    
    # Create all tasks
    print(f"Creating {len(pages)} async tasks...")
    metafields_tasks = [
        client.get_page_metafields(page.id) 
        for page in pages
    ]
    
    # Execute all in parallel
    print(f"Executing {len(metafields_tasks)} tasks in parallel...")
    metafields_list = await asyncio.gather(*metafields_tasks, return_exceptions=True)
    
    total_duration = time.time() - start_time
    
    # Count successes vs errors
    successes = sum(1 for m in metafields_list if not isinstance(m, Exception))
    errors = sum(1 for m in metafields_list if isinstance(m, Exception))
    
    print(f"\n✅ Parallel Total: {total_duration:.2f}s")
    print(f"   Successes: {successes}/{len(pages)}")
    print(f"   Errors: {errors}/{len(pages)}")
    
    return total_duration, metafields_list


# ══════════════════════════════════════════════════════════════════════════
# BENCHMARK: FULL SYNC
# ══════════════════════════════════════════════════════════════════════════

async def benchmark_full_sync(
    sync_service: ShopifyKBSyncService
) -> Tuple[float, int, int]:
    """
    Benchmark full sync operation (current implementation).
    
    Args:
        sync_service: ShopifyKBSyncService instance
        
    Returns:
        (duration_seconds, successful_count, failed_count)
    """
    print("\n" + "=" * 70)
    print("BENCHMARK: Full Sync (End-to-End)")
    print("=" * 70)
    
    start_time = time.time()
    
    # Run full sync
    report = await sync_service.sync_all_pages()
    
    total_duration = time.time() - start_time
    
    print(f"\n✅ Full Sync Completed: {total_duration:.2f}s")
    print(f"   Total pages: {report.total_pages}")
    print(f"   Successful: {report.successful}")
    print(f"   Failed: {report.failed}")
    print(f"   Skipped: {report.skipped}")
    print(f"   Errors: {len(report.errors)}")
    
    if report.errors:
        print("\n⚠️ Errors encountered:")
        for error in report.errors[:5]:  # Show first 5
            print(f"   - {error}")
    
    return total_duration, report.successful, report.failed


# ══════════════════════════════════════════════════════════════════════════
# MAIN TEST RUNNER
# ══════════════════════════════════════════════════════════════════════════

async def main():
    """Run all parallelization benchmarks."""
    
    print("\n" + "=" * 70)
    print("SYNC PARALLELIZATION - PERFORMANCE VALIDATION")
    print("=" * 70)
    print(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 70)
    
    # ─────────────────────────────────────────────────────────────────────
    # SETUP
    # ─────────────────────────────────────────────────────────────────────
    
    print("\n📋 SETUP")
    print("-" * 70)
    
    # Initialize clients
    print("Initializing Shopify KB Client...")
    client = ShopifyKBClient(
        shop_url=settings.SHOPIFY_SHOP_URL,
        access_token=settings.SHOPIFY_ACCESS_TOKEN,
        webhook_secret=settings.SHOPIFY_WEBHOOK_SECRET
    )
    
    print("Initializing Database Pool...")
    db_pool = await asyncpg.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        min_size=2,
        max_size=10
    )
    
    print("Initializing Redis Client...")
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    
    print("Initializing Sync Service...")
    sync_service = ShopifyKBSyncService(
        shopify_client=client,
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    print("✅ Setup complete")
    
    # ─────────────────────────────────────────────────────────────────────
    # FETCH PAGES (Setup for benchmarks)
    # ─────────────────────────────────────────────────────────────────────
    
    print("\n📄 Fetching pages from Shopify...")
    all_pages_data = client.get_pages(limit=None)
    
    # Parse to Pydantic models
    pages = []
    for page_data in all_pages_data:
        try:
            page = ShopifyPage(**page_data)
            pages.append(page)
        except Exception as e:
            print(f"⚠️ Failed to parse page: {e}")
            continue
    
    print(f"✅ Fetched {len(pages)} pages total")
    
    # ─────────────────────────────────────────────────────────────────────
    # TEST 1: Sequential vs Parallel Metafields Fetch
    # ─────────────────────────────────────────────────────────────────────
    
    # Use first 6 pages for focused benchmark
    test_pages = pages[:6]
    
    print(f"\n🔬 Running benchmarks with {len(test_pages)} pages...")
    
    # Sequential benchmark
    seq_duration, seq_metafields = await benchmark_sequential_metafields(
        client, test_pages
    )
    
    # Parallel benchmark
    par_duration, par_metafields = await benchmark_parallel_metafields(
        client, test_pages
    )
    
    # Calculate improvement
    improvement_pct = ((seq_duration - par_duration) / seq_duration) * 100
    speedup = seq_duration / par_duration
    
    print("\n" + "=" * 70)
    print("RESULTS: Metafields Fetch Comparison")
    print("=" * 70)
    print(f"Sequential Time:  {seq_duration:.2f}s")
    print(f"Parallel Time:    {par_duration:.2f}s")
    print(f"Improvement:      {improvement_pct:.1f}%")
    print(f"Speedup:          {speedup:.2f}x faster")
    print("=" * 70)
    
    # ─────────────────────────────────────────────────────────────────────
    # TEST 2: Full Sync Benchmark
    # ─────────────────────────────────────────────────────────────────────
    
    sync_duration, successful, failed = await benchmark_full_sync(sync_service)
    
    print("\n" + "=" * 70)
    print("RESULTS: Full Sync Performance")
    print("=" * 70)
    print(f"Total Duration:   {sync_duration:.2f}s")
    print(f"Pages Synced:     {successful}")
    print(f"Success Rate:     {(successful / len(pages) * 100):.1f}%")
    print(f"Avg per page:     {(sync_duration / successful):.2f}s")
    print("=" * 70)
    
    # ─────────────────────────────────────────────────────────────────────
    # VALIDATION: Verify all pages are in PostgreSQL
    # ─────────────────────────────────────────────────────────────────────
    
    print("\n✅ VALIDATION: Checking PostgreSQL...")
    
    query = "SELECT COUNT(*) FROM kb_content"
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(query)
    
    print(f"   Pages in PostgreSQL: {count}")
    
    if count >= successful:
        print("   ✅ All synced pages are in database")
    else:
        print(f"   ⚠️ Mismatch: {successful} synced but only {count} in DB")
    
    # ─────────────────────────────────────────────────────────────────────
    # VALIDATION: Verify Redis cache
    # ─────────────────────────────────────────────────────────────────────
    
    print("\n✅ VALIDATION: Checking Redis cache...")
    
    kb_keys = redis_client.keys("kb:*")
    print(f"   Cache keys: {len(kb_keys)}")
    
    if kb_keys:
        print("   ✅ Cache is populated")
        # Show sample keys
        print(f"   Sample keys: {kb_keys[:3]}")
    else:
        print("   ⚠️ Cache is empty")
    
    # ─────────────────────────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────────────────────────
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    
    print("\n🎯 OPTIMIZATION IMPACT:")
    print(f"   Metafields fetch improved by {improvement_pct:.1f}%")
    print(f"   Parallel execution is {speedup:.2f}x faster")
    
    print("\n📊 SYSTEM STATUS:")
    print(f"   PostgreSQL records: {count}")
    print(f"   Redis cache keys: {len(kb_keys)}")
    print(f"   Sync success rate: {(successful / len(pages) * 100):.1f}%")
    
    print("\n✨ PROJECTED SCALABILITY:")
    pages_20 = 20
    seq_20 = (seq_duration / len(test_pages)) * pages_20
    par_20 = par_duration  # Parallel time doesn't scale linearly
    
    print(f"   20 pages sequential: ~{seq_20:.1f}s")
    print(f"   20 pages parallel: ~{par_20:.1f}s")
    print(f"   Improvement with 20 pages: {((seq_20 - par_20) / seq_20) * 100:.1f}%")
    
    print("\n" + "=" * 70)
    print("✅ VALIDATION COMPLETE")
    print("=" * 70)
    
    # Cleanup
    await db_pool.close()
    redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
