"""
Test incremental de semaphore con validación de race conditions
"""
import asyncio
import time
import os
import sys
from typing import List, Dict, Any

from src.api.dependencies import get_kb_sync_service, get_db_pool

async def validate_data_integrity(db_pool) -> Dict[str, Any]:
    """
    Validar integridad de datos después del sync.
    
    Returns:
        Dict con resultados de validación
    """
    async with db_pool.acquire() as conn:
        # Check 1: Contar registros
        count = await conn.fetchval("SELECT COUNT(*) FROM kb_contents")
        
        # Check 2: Verificar no hay NULL values en campos críticos
        null_content = await conn.fetchval(
            "SELECT COUNT(*) FROM kb_contents WHERE content IS NULL"
        )
        null_title = await conn.fetchval(
            "SELECT COUNT(*) FROM kb_contents WHERE title IS NULL"
        )
        
        # Check 3: Verificar timestamps válidos
        invalid_timestamps = await conn.fetchval(
            "SELECT COUNT(*) FROM kb_contents WHERE updated_at < created_at"
        )
        
        # Check 4: Verificar unique constraint (no duplicados)
        duplicates = await conn.fetch("""
            SELECT sub_intent, language, COALESCE(category, 'general') as cat, COUNT(*)
            FROM kb_contents
            GROUP BY sub_intent, language, cat
            HAVING COUNT(*) > 1
        """)
        
    return {
        "total_records": count,
        "null_content": null_content,
        "null_title": null_title,
        "invalid_timestamps": invalid_timestamps,
        "duplicates": len(duplicates),
        "duplicate_details": [dict(d) for d in duplicates]
    }

async def test_race_conditions(semaphore_size: int) -> Dict[str, Any]:
    """
    Test race conditions ejecutando 3 syncs concurrentes.
    
    Args:
        semaphore_size: Tamaño de semaphore a testear
        
    Returns:
        Dict con resultados del test
    """
    print(f"\n🧪 Testing semaphore={semaphore_size} with race conditions...")
    print("-" * 70)
    
    # Configurar environment variable
    os.environ["KB_SYNC_SEMAPHORE_SIZE"] = str(semaphore_size)
    
    # Get services (forzar recarga)
    sync_service = await get_kb_sync_service()
    db_pool = await get_db_pool()
    
    # Validar estado ANTES
    print("📊 Validating data BEFORE concurrent syncs...")
    before = await validate_data_integrity(db_pool)
    print(f"  ✅ Records before: {before['total_records']}")
    
    # Ejecutar 3 syncs CONCURRENTEMENTE
    print(f"\n⚡ Running 3 concurrent syncs with semaphore={semaphore_size}...")
    start = time.time()
    
    results = await asyncio.gather(
        sync_service.sync_all_pages(),
        sync_service.sync_all_pages(),
        sync_service.sync_all_pages(),
        return_exceptions=True
    )
    
    duration = time.time() - start
    
    # Check for exceptions
    exceptions = [r for r in results if isinstance(r, Exception)]
    if exceptions:
        print(f"\n❌ ERRORS during concurrent sync:")
        for e in exceptions:
            print(f"  - {type(e).__name__}: {e}")
        return {
            "success": False,
            "semaphore_size": semaphore_size,
            "errors": [str(e) for e in exceptions]
        }
    
    reports = [r for r in results if not isinstance(r, Exception)]
    
    print(f"✅ All 3 syncs completed in {duration:.2f}s")
    print(f"  Average: {duration / 3:.2f}s per sync")
    
    # Validar estado DESPUÉS
    print("\n📊 Validating data AFTER concurrent syncs...")
    after = await validate_data_integrity(db_pool)
    
    # Verificar integridad
    issues = []
    
    if after['total_records'] != before['total_records']:
        issues.append(f"Record count mismatch: {before['total_records']} → {after['total_records']}")
    
    if after['null_content'] > 0:
        issues.append(f"Found {after['null_content']} NULL content values")
    
    if after['null_title'] > 0:
        issues.append(f"Found {after['null_title']} NULL title values")
    
    if after['invalid_timestamps'] > 0:
        issues.append(f"Found {after['invalid_timestamps']} invalid timestamps")
    
    if after['duplicates'] > 0:
        issues.append(f"Found {after['duplicates']} duplicate records: {after['duplicate_details']}")
    
    # Resultado
    if not issues:
        print("✅ DATA INTEGRITY CHECK PASSED")
        print(f"  - Records: {after['total_records']}")
        print(f"  - No NULL values")
        print(f"  - Valid timestamps")
        print(f"  - No duplicates")
        return {
            "success": True,
            "semaphore_size": semaphore_size,
            "duration": duration,
            "avg_duration": duration / 3,
            "data_integrity": "PASS"
        }
    else:
        print("❌ DATA INTEGRITY CHECK FAILED")
        for issue in issues:
            print(f"  - {issue}")
        return {
            "success": False,
            "semaphore_size": semaphore_size,
            "data_integrity": "FAIL",
            "issues": issues
        }

async def run_incremental_test():
    """
    Test incremental: 1 → 2 → 3 → 5 → 10
    """
    print("=" * 70)
    print("INCREMENTAL SEMAPHORE TESTING")
    print("=" * 70)
    
    test_values = [1, 2, 3, 5, 10]
    results = []
    
    for semaphore_size in test_values:
        result = await test_race_conditions(semaphore_size)
        results.append(result)
        
        if not result["success"]:
            print(f"\n🚨 STOPPED at semaphore={semaphore_size} due to failure")
            break
        
        # Brief pause entre tests
        await asyncio.sleep(2)
    
    # Resumen
    print("\n" + "=" * 70)
    print("TEST RESULTS SUMMARY")
    print("=" * 70)
    
    for result in results:
        if result["success"]:
            print(f"✅ semaphore={result['semaphore_size']}: PASS ({result['avg_duration']:.2f}s avg)")
        else:
            print(f"❌ semaphore={result['semaphore_size']}: FAIL")
    
    # Recomendación
    successful_values = [r['semaphore_size'] for r in results if r['success']]
    if successful_values:
        max_safe = max(successful_values)
        print(f"\n🎯 RECOMMENDATION: Use semaphore={max_safe} for production")
        print(f"   Expected speedup: ~{max_safe}x faster")
    
    print("=" * 70)
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(run_incremental_test())
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)