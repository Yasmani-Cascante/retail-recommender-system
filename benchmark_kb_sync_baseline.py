"""
Benchmark performance actual del KB sync

Este script mide el performance baseline del sistema de sincronización
de Knowledge Base con la configuración actual (semaphore=1).

Author: Yasmani Roque
Date: 13 Feb 2026
Part of: M1 Optimize Sync Performance
"""
import asyncio
import time
import sys
import statistics
from pathlib import Path
from typing import Dict, Any

# ✅ CRÍTICO: Cargar variables de entorno ANTES de importar cualquier módulo del proyecto
from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
project_root = Path(__file__).parent
env_path = project_root / ".env"
load_dotenv(env_path)

print(f"✅ Loading .env from: {env_path}")
print(f"✅ .env exists: {env_path.exists()}")

# Verificar que variables críticas estén cargadas
import os
shop_url = os.getenv("SHOPIFY_SHOP_URL")
access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
print(f"✅ SHOPIFY_SHOP_URL: {shop_url}")
print(f"✅ SHOPIFY_ACCESS_TOKEN: {'***' + access_token[-4:] if access_token else 'NOT SET'}")

if not shop_url or not access_token:
    print("❌ ERROR: Shopify credentials not found in .env")
    sys.exit(1)

# Ahora sí, importar módulos del proyecto
from src.api.dependencies import (
    get_kb_sync_service,
    get_db_pool
)

async def run_baseline_benchmark() -> Dict[str, Any]:
    """
    Medir performance actual con semaphore=1
    
    Returns:
        Dict con métricas: median, mean, stdev, min, max, runs
    """
    print("=" * 70)
    print("KB SYNC PERFORMANCE BASELINE")
    print("=" * 70)
    
    # Setup
    print("\n🔧 Initializing services...")
    sync_service = await get_kb_sync_service()
    db_pool = await get_db_pool()
    
    # Verify shopify client
    if sync_service.shopify is None:
        print("❌ ERROR: ShopifyKBClient is None!")
        print("   This should not happen if .env is loaded correctly.")
        sys.exit(1)
    
    print(f"✅ ShopifyKBClient: {type(sync_service.shopify).__name__}")
    
    # Verify DB state
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM kb_contents")
        pages = await conn.fetchval(
            "SELECT COUNT(DISTINCT shopify_page_id) FROM kb_contents"
        )
        print(f"✅ DB Records: {count}")
        print(f"✅ Unique Pages: {pages}")
    
    # Warm-up run (ignorar)
    print("\n🔥 Warm-up run...")
    try:
        await sync_service.sync_all_pages()
        print("✅ Warm-up completed")
    except Exception as e:
        print(f"❌ Warm-up failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Benchmark runs (5 veces para stats confiables)
    print("\n📊 Baseline benchmark (5 runs)...")
    print("-" * 70)
    
    durations = []
    
    for i in range(1, 6):
        print(f"\n▶ Run {i}/5")
        start = time.time()
        
        try:
            report = await sync_service.sync_all_pages()
            duration = time.time() - start
            
            durations.append(duration)
            
            # Métricas por run
            throughput = report.total_pages / duration if duration > 0 else 0
            success_rate = (report.successful / report.total_pages * 100) if report.total_pages > 0 else 0
            
            print(f"  ✅ Duration: {duration:.2f}s")
            print(f"  ✅ Pages: {report.total_pages}")
            print(f"  ✅ Successful: {report.successful}")
            print(f"  ✅ Failed: {report.failed}")
            print(f"  ✅ Throughput: {throughput:.2f} pages/sec")
            print(f"  ✅ Success Rate: {success_rate:.1f}%")
            
        except Exception as e:
            print(f"  ❌ Run {i} failed: {e}")
            import traceback
            traceback.print_exc()
            # Continuar con siguiente run
    
    if not durations:
        print("\n❌ No successful runs completed!")
        sys.exit(1)
    
    # Calcular estadísticas
    median = statistics.median(durations)
    mean = statistics.mean(durations)
    stdev = statistics.stdev(durations) if len(durations) > 1 else 0
    min_duration = min(durations)
    max_duration = max(durations)
    
    print("\n" + "=" * 70)
    print("BASELINE RESULTS:")
    print("=" * 70)
    print(f"Median: {median:.2f}s")
    print(f"Mean: {mean:.2f}s")
    print(f"StdDev: {stdev:.2f}s")
    print(f"Min: {min_duration:.2f}s")
    print(f"Max: {max_duration:.2f}s")
    print(f"Throughput (median): {report.total_pages / median:.2f} pages/sec")
    print("=" * 70)
    
    return {
        "median": median,
        "mean": mean,
        "stdev": stdev,
        "min": min_duration,
        "max": max_duration,
        "runs": durations,
        "total_pages": report.total_pages
    }

if __name__ == "__main__":
    try:
        result = asyncio.run(run_baseline_benchmark())
        
        print("\n✅ Benchmark completed successfully!")
        print(f"\n🎯 KEY METRIC: {result['median']:.2f}s for {result['total_pages']} pages")
        print(f"🎯 Target with optimization: {result['median'] / 5:.2f}s (5x faster)")
        
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)