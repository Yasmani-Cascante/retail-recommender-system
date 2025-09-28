# backup_emergency_cache_before_migration.py
"""
Backup script antes de migrar a product_cache.py
"""

import shutil
import time
from pathlib import Path

def create_backup():
    timestamp = int(time.time())
    
    # Backup current products_router.py
    source = "src/api/routers/products_router.py"
    backup = f"src/api/routers/products_router.py.backup_before_product_cache_{timestamp}"
    
    try:
        shutil.copy2(source, backup)
        print(f"✅ Backup created: {backup}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

if __name__ == "__main__":
    print("📦 Creating backup before product_cache migration...")
    success = create_backup()
    if success:
        print("✅ Ready for migration to product_cache.py")
    else:
        print("❌ Migration aborted - backup failed")
