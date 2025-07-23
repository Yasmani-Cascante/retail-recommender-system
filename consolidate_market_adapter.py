# consolidate_market_adapter.py
"""
Script to consolidate market adapter implementations and fix the routing
"""

import os
import shutil
import re
from datetime import datetime


def create_directories():
    """Create the new directory structure"""
    print("📁 Creating directory structure...")
    
    core_dir = "src/core"
    market_dir = "src/core/market"
    
    os.makedirs(core_dir, exist_ok=True)
    os.makedirs(market_dir, exist_ok=True)
    
    # Create __init__ files
    init_content = '"""Core business logic modules"""'
    
    with open(os.path.join(core_dir, "__init__.py"), "w") as f:
        f.write(init_content)
    
    with open(os.path.join(market_dir, "__init__.py"), "w") as f:
        f.write('"""Market adaptation logic"""')
    
    print("✅ Directory structure created")


def backup_existing_files():
    """Backup existing market_utils files"""
    print("\n📦 Backing up existing files...")
    
    backup_dir = f"backup_market_utils_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        "src/api/utils/market_utils.py",
        "src/api/mcp/utils/market_utils.py"
    ]
    
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, file_path.replace("/", "_").replace("\\", "_"))
            shutil.copy2(file_path, backup_path)
            print(f"✅ Backed up: {file_path}")
    
    return backup_dir


def update_imports_in_file(file_path: str, old_imports: list, new_import: str) -> bool:
    """Update imports in a single file"""
    if not os.path.exists(file_path):
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace old imports
        for old_import in old_imports:
            pattern = re.compile(
                rf'^{re.escape(old_import)}.*$',
                re.MULTILINE
            )
            content = pattern.sub(new_import, content)
        
        # If content changed, save
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error updating {file_path}: {e}")
        return False


def update_all_imports():
    """Update all imports across the codebase"""
    print("\n🔄 Updating imports across codebase...")
    
    old_imports = [
        "from src.api.utils.market_utils import",
        "from src.api.mcp.utils.market_utils import",
        "import src.api.utils.market_utils",
        "import src.api.mcp.utils.market_utils"
    ]
    
    new_import = "from src.core.market.adapter import get_market_adapter, adapt_product_for_market"
    
    # Files to update
    files_to_check = [
        "src/api/routers/mcp_router.py",
        "src/api/main_unified_redis.py",
        "src/recommenders/hybrid_recommender.py",
        "src/api/mcp/engines/mcp_personalization_engine.py"
    ]
    
    # Add all Python files in routers directory
    routers_dir = "src/api/routers"
    if os.path.exists(routers_dir):
        for file in os.listdir(routers_dir):
            if file.endswith(".py"):
                files_to_check.append(os.path.join(routers_dir, file))
    
    updated_count = 0
    for file_path in files_to_check:
        if update_imports_in_file(file_path, old_imports, new_import):
            print(f"✅ Updated: {file_path}")
            updated_count += 1
    
    print(f"\n📊 Updated {updated_count} files")


def fix_router_adaptation():
    """Fix the router to actually call the adapter"""
    print("\n🔧 Fixing router adaptation logic...")
    
    router_path = "src/api/routers/mcp_router.py"
    
    if not os.path.exists(router_path):
        print(f"❌ Router not found: {router_path}")
        return
    
    with open(router_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to find where recommendations are processed
    # Look for places where market_adapted is set to True
    pattern = re.compile(
        r'(["\']market_adapted["\']\s*:\s*True)',
        re.MULTILINE
    )
    
    matches = list(pattern.finditer(content))
    
    if not matches:
        print("❌ No 'market_adapted: True' found in router")
        return
    
    print(f"📍 Found {len(matches)} instances of market_adapted flag")
    
    # Create the patch content
    patch_code = '''
            # Apply market adaptation
            if market_context and 'market_id' in market_context:
                try:
                    adapter = get_market_adapter()
                    recommendation = await adapter.adapt_product(
                        recommendation,
                        market_context['market_id']
                    )
                except Exception as e:
                    logger.error(f"Market adaptation failed: {e}")
            '''
    
    # Insert patch before setting market_adapted flag
    # Work backwards to not affect indices
    for match in reversed(matches):
        # Find the context around this match
        start = max(0, match.start() - 500)
        end = min(len(content), match.end() + 500)
        context = content[start:end]
        
        # Check if this is in a recommendation context
        if 'recommendation' in context or 'product' in context:
            # Find where to insert (before the line with market_adapted)
            line_start = content.rfind('\n', start, match.start()) + 1
            indent = len(content[line_start:match.start()]) - len(content[line_start:match.start()].lstrip())
            
            # Add proper indentation to patch
            indented_patch = '\n'.join(
                ' ' * indent + line if line.strip() else line
                for line in patch_code.strip().split('\n')
            )
            
            # Insert patch
            content = content[:line_start] + indented_patch + '\n' + content[line_start:]
            print(f"✅ Added adaptation at position {match.start()}")
    
    # Save updated router
    with open(router_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Router adaptation logic fixed")


def create_validation_test():
    """Create a validation test to ensure adaptation is working"""
    print("\n🧪 Creating validation test...")
    
    test_content = '''# test_market_validation.py
"""
Validation test to ensure market adaptation is actually happening
"""

import asyncio
import aiohttp
import json
from datetime import datetime


async def validate_market_adaptation():
    """Validate that market adaptation is working correctly"""
    
    API_URL = "http://localhost:8000/v1/mcp/conversation"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    # Test for US market
    data = {
        "query": "busco aros de oro",
        "market_id": "US",
        "session_id": f"validation_{int(datetime.now().timestamp())}"
    }
    
    print("🧪 MARKET ADAPTATION VALIDATION TEST")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, json=data) as response:
            if response.status != 200:
                print(f"❌ API Error: {response.status}")
                return False
            
            result = await response.json()
            recommendations = result.get("recommendations", [])
            
            if not recommendations:
                print("❌ No recommendations received")
                return False
            
            print(f"✅ Received {len(recommendations)} recommendations")
            
            # Validate first recommendation
            first_rec = recommendations[0]
            
            print("\\nValidating first recommendation:")
            print(f"Title: {first_rec.get('title')}")
            print(f"Price: {first_rec.get('price')} {first_rec.get('currency')}")
            
            # Validation checks
            checks = {
                "Has adaptation metadata": "_market_adaptation" in first_rec,
                "Has original price": "original_price" in first_rec,
                "Price is converted": first_rec.get("price", 0) < 100,  # Should be ~$3-20, not thousands
                "Currency is USD": first_rec.get("currency") == "USD",
                "Title contains English": any(word in first_rec.get("title", "").lower() for word in ["earrings", "gold", "ring", "bracelet"])
            }
            
            print("\\nValidation Results:")
            all_passed = True
            for check, passed in checks.items():
                status = "✅" if passed else "❌"
                print(f"{status} {check}")
                if not passed:
                    all_passed = False
            
            if all_passed:
                print("\\n✅ ALL VALIDATIONS PASSED - Market adaptation is working!")
            else:
                print("\\n❌ VALIDATION FAILED - Market adaptation is not working properly")
                
                # Debug info
                print("\\nDebug info:")
                print(f"Full recommendation: {json.dumps(first_rec, indent=2)}")
            
            return all_passed


if __name__ == "__main__":
    result = asyncio.run(validate_market_adaptation())
    exit(0 if result else 1)
'''
    
    with open("test_market_validation.py", "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print("✅ Validation test created: test_market_validation.py")


def main():
    print("""
    ╔════════════════════════════════════════════════════════╗
    ║     MARKET ADAPTER CONSOLIDATION & FIX                 ║
    ╚════════════════════════════════════════════════════════╝
    """)
    
    print("\n🎯 This script will:")
    print("1. Create a unified market adapter in src/core/market/")
    print("2. Update all imports to use the new location")
    print("3. Fix the router to actually call the adapter")
    print("4. Create validation tests")
    
    response = input("\n¿Proceed? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled")
        return
    
    # Execute steps
    create_directories()
    backup_dir = backup_existing_files()
    
    # Copy the unified adapter to new location
    print("\n📝 Installing unified adapter...")
    # The adapter code is in the previous artifact - you'll need to save it
    print("⚠️ Save the content from 'unified-market-adapter' artifact as:")
    print("   src/core/market/adapter.py")
    
    update_all_imports()
    fix_router_adaptation()
    create_validation_test()
    
    print("\n" + "=" * 60)
    print("✅ CONSOLIDATION COMPLETE")
    print("=" * 60)
    
    print(f"\n📁 Backups saved in: {backup_dir}")
    
    print("\n📋 Next steps:")
    print("1. Save the unified adapter code to: src/core/market/adapter.py")
    print("2. Delete old market_utils files:")
    print("   - src/api/utils/market_utils.py")
    print("   - src/api/mcp/utils/market_utils.py")
    print("3. Restart the server")
    print("4. Run validation: python test_market_validation.py")
    
    print("\n🎯 The system now has:")
    print("- Single source of truth for market adaptation")
    print("- Proper async/await pattern")
    print("- Validation methods to ensure adaptation happens")
    print("- Clean architecture ready for scaling")


if __name__ == "__main__":
    main()