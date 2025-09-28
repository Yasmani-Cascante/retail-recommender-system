#!/usr/bin/env python3
"""
Enterprise Regression Diagnostic Script
======================================

Diagnosticar regresión en arquitectura enterprise post-migración.
Identifica problemas de service instance confusion y configuration drift.

Author: CTO Strategy Team
Priority: CRITICAL - Regression diagnosis
Timeline: Day 1-2 implementation
"""

import asyncio
import time
import logging
import sys
import os
from typing import Dict, Optional, Any
from datetime import datetime

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnterpriseRegressionDiagnostic:
    """
    Diagnosticar regresión en arquitectura enterprise post-migración
    """
    
    def __init__(self):
        self.service_factory = None
        self.hybrid_recommender = None
        self.enterprise_cache = None
        self.redis_service = None
        self.diagnosis_results = {}
    
    async def initialize_components(self):
        """Initialize enterprise components for diagnosis"""
        try:
            logger.info("🔧 Initializing enterprise components for diagnosis...")
            
            # Import ServiceFactory
            from src.api.factories import ServiceFactory
            self.service_factory = ServiceFactory
            
            # Get enterprise ProductCache
            self.enterprise_cache = await ServiceFactory.get_product_cache_singleton()
            logger.info("✅ Enterprise ProductCache singleton obtained")
            
            # Get Redis service
            self.redis_service = await ServiceFactory.get_redis_service()
            logger.info("✅ Enterprise Redis service obtained")
            
            # Try to get hybrid recommender from global variables
            # (You may need to adapt this based on your global variable structure)
            try:
                import src.api.main_unified_redis as main_module
                if hasattr(main_module, 'hybrid_recommender'):
                    self.hybrid_recommender = main_module.hybrid_recommender
                    logger.info("✅ HybridRecommender obtained from main module")
                else:
                    logger.warning("⚠️ HybridRecommender not found in main module")
            except ImportError as e:
                logger.warning(f"⚠️ Could not import main module: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize components: {e}")
            return False
    
    async def diagnose_productcache_instances(self):
        """Verificar si múltiples instances de ProductCache existen"""
        try:
            logger.info("🔍 Diagnosing ProductCache instances...")
            
            if not self.enterprise_cache:
                logger.error("❌ Enterprise cache not available")
                return False
            
            enterprise_id = id(self.enterprise_cache)
            logger.info(f"📋 Enterprise ProductCache ID: {enterprise_id}")
            
            # Check if HybridRecommender uses same instance
            if self.hybrid_recommender:
                hybrid_cache = getattr(self.hybrid_recommender, 'product_cache', None)
                hybrid_id = id(hybrid_cache) if hybrid_cache else None
                
                logger.info(f"📋 Hybrid ProductCache ID: {hybrid_id}")
                
                if enterprise_id != hybrid_id:
                    logger.error("❌ REGRESSION: Multiple ProductCache instances detected!")
                    logger.error(f"   Enterprise: {enterprise_id}")
                    logger.error(f"   Hybrid: {hybrid_id}")
                    self.diagnosis_results['productcache_instances'] = {
                        'status': 'REGRESSION',
                        'enterprise_id': enterprise_id,
                        'hybrid_id': hybrid_id,
                        'issue': 'Multiple instances - cache misses expected'
                    }
                    return False
                else:
                    logger.info("✅ ProductCache instances aligned correctly")
                    self.diagnosis_results['productcache_instances'] = {
                        'status': 'OK',
                        'enterprise_id': enterprise_id,
                        'hybrid_id': hybrid_id
                    }
                    return True
            else:
                logger.warning("⚠️ HybridRecommender not available for comparison")
                self.diagnosis_results['productcache_instances'] = {
                    'status': 'WARNING',
                    'enterprise_id': enterprise_id,
                    'hybrid_id': None,
                    'issue': 'Cannot compare - HybridRecommender not accessible'
                }
                return None
                
        except Exception as e:
            logger.error(f"❌ ProductCache diagnosis failed: {e}")
            self.diagnosis_results['productcache_instances'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            return False
    
    async def diagnose_redis_connections(self):
        """Verificar Redis connection consistency"""
        try:
            logger.info("🔍 Diagnosing Redis connections...")
            
            if not self.redis_service or not self.enterprise_cache:
                logger.error("❌ Required services not available")
                return False
            
            # Enterprise Redis client
            enterprise_client = getattr(self.redis_service, '_client', None)
            enterprise_client_id = id(enterprise_client) if enterprise_client else None
            
            # ProductCache Redis client
            cache_redis_client = getattr(self.enterprise_cache, 'redis_client', None) or getattr(self.enterprise_cache, 'redis', None)
            cache_client_id = id(cache_redis_client) if cache_redis_client else None
            
            logger.info(f"📋 Enterprise Redis client ID: {enterprise_client_id}")
            logger.info(f"📋 Cache Redis client ID: {cache_client_id}")
            
            if enterprise_client_id and cache_client_id:
                if enterprise_client_id != cache_client_id:
                    logger.warning("⚠️ Different Redis clients detected - connection pooling not optimized")
                    self.diagnosis_results['redis_connections'] = {
                        'status': 'SUBOPTIMAL',
                        'enterprise_client_id': enterprise_client_id,
                        'cache_client_id': cache_client_id,
                        'issue': 'Different Redis clients - pooling not shared'
                    }
                    return False
                else:
                    logger.info("✅ Redis clients aligned - connection pooling optimized")
                    self.diagnosis_results['redis_connections'] = {
                        'status': 'OK',
                        'enterprise_client_id': enterprise_client_id,
                        'cache_client_id': cache_client_id
                    }
                    return True
            else:
                logger.warning("⚠️ Could not access Redis client instances")
                self.diagnosis_results['redis_connections'] = {
                    'status': 'WARNING',
                    'enterprise_client_id': enterprise_client_id,
                    'cache_client_id': cache_client_id,
                    'issue': 'Cannot access Redis client instances'
                }
                return None
                
        except Exception as e:
            logger.error(f"❌ Redis connection diagnosis failed: {e}")
            self.diagnosis_results['redis_connections'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            return False
    
    async def diagnose_service_health(self):
        """Verificar health status de enterprise services"""
        try:
            logger.info("🔍 Diagnosing enterprise service health...")
            
            # Import HealthCompositionRoot
            from src.api.factories import HealthCompositionRoot
            
            health_check = await HealthCompositionRoot.comprehensive_health_check()
            
            overall_status = health_check.get('overall_status', 'unknown')
            logger.info(f"📋 Overall system health: {overall_status}")
            
            self.diagnosis_results['service_health'] = {
                'status': overall_status,
                'health_report': health_check
            }
            
            if overall_status == 'healthy':
                logger.info("✅ Enterprise services healthy")
                return True
            else:
                logger.warning(f"⚠️ Enterprise services degraded: {overall_status}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Service health diagnosis failed: {e}")
            self.diagnosis_results['service_health'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            return False
    
    async def diagnose_cache_performance(self):
        """Verificar cache performance metrics"""
        try:
            logger.info("🔍 Diagnosing cache performance...")
            
            if not self.enterprise_cache:
                logger.error("❌ Enterprise cache not available")
                return False
            
            # Get cache stats
            if hasattr(self.enterprise_cache, 'get_stats'):
                stats = self.enterprise_cache.get_stats()
                hit_ratio = stats.get('hit_ratio', 0)
                total_requests = stats.get('total_requests', 0)
                redis_hits = stats.get('redis_hits', 0)
                redis_misses = stats.get('redis_misses', 0)
                
                logger.info(f"📊 Cache Statistics:")
                logger.info(f"   Hit Ratio: {hit_ratio:.2%}")
                logger.info(f"   Total Requests: {total_requests}")
                logger.info(f"   Redis Hits: {redis_hits}")
                logger.info(f"   Redis Misses: {redis_misses}")
                
                self.diagnosis_results['cache_performance'] = {
                    'hit_ratio': hit_ratio,
                    'total_requests': total_requests,
                    'redis_hits': redis_hits,
                    'redis_misses': redis_misses,
                    'stats': stats
                }
                
                if hit_ratio > 0.6:
                    logger.info("✅ Cache performance optimal")
                    return True
                elif hit_ratio > 0.3:
                    logger.warning("⚠️ Cache performance suboptimal")
                    return False
                else:
                    logger.error("❌ Cache performance critical - regression confirmed")
                    return False
            else:
                logger.warning("⚠️ Cache stats not available")
                return None
                
        except Exception as e:
            logger.error(f"❌ Cache performance diagnosis failed: {e}")
            self.diagnosis_results['cache_performance'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            return False
    
    async def run_comprehensive_diagnosis(self):
        """Run complete enterprise regression diagnosis"""
        logger.info("🚀 STARTING COMPREHENSIVE ENTERPRISE REGRESSION DIAGNOSIS")
        logger.info("=" * 70)
        
        # Initialize components
        if not await self.initialize_components():
            logger.error("❌ Failed to initialize - aborting diagnosis")
            return False
        
        # Run diagnostics
        diagnostics = [
            ("ProductCache Instances", self.diagnose_productcache_instances),
            ("Redis Connections", self.diagnose_redis_connections),
            ("Service Health", self.diagnose_service_health),
            ("Cache Performance", self.diagnose_cache_performance)
        ]
        
        results = {}
        
        for name, diagnostic_func in diagnostics:
            logger.info(f"\n🔍 Running {name} diagnosis...")
            try:
                result = await diagnostic_func()
                results[name] = result
                
                if result is True:
                    logger.info(f"✅ {name}: PASSED")
                elif result is False:
                    logger.error(f"❌ {name}: FAILED")
                else:
                    logger.warning(f"⚠️ {name}: INCONCLUSIVE")
                    
            except Exception as e:
                logger.error(f"❌ {name} diagnosis crashed: {e}")
                results[name] = False
        
        # Generate final report
        await self.generate_diagnosis_report(results)
        
        return results
    
    async def generate_diagnosis_report(self, results: Dict):
        """Generate comprehensive diagnosis report"""
        logger.info("\n📋 ENTERPRISE REGRESSION DIAGNOSIS REPORT")
        logger.info("=" * 50)
        
        passed = sum(1 for r in results.values() if r is True)
        failed = sum(1 for r in results.values() if r is False)
        inconclusive = sum(1 for r in results.values() if r is None)
        
        logger.info(f"📊 Summary: {passed} passed, {failed} failed, {inconclusive} inconclusive")
        
        # Detailed results
        for test_name, result in results.items():
            status_icon = "✅" if result is True else "❌" if result is False else "⚠️"
            logger.info(f"{status_icon} {test_name}: {result}")
        
        # Regression analysis
        if failed > 0:
            logger.error("🚨 REGRESSION CONFIRMED: Enterprise architecture issues detected")
            logger.error("📋 Recommended actions:")
            
            if 'ProductCache Instances' in results and results['ProductCache Instances'] is False:
                logger.error("   1. Fix ProductCache instance alignment")
            
            if 'Redis Connections' in results and results['Redis Connections'] is False:
                logger.error("   2. Optimize Redis connection pooling")
            
            if 'Cache Performance' in results and results['Cache Performance'] is False:
                logger.error("   3. Investigate cache miss root cause")
        
        elif passed == len(results):
            logger.info("✅ NO REGRESSION DETECTED: Enterprise architecture healthy")
            logger.info("📋 Cache miss issue may be elsewhere - check:")
            logger.info("   1. Timing of service initialization")
            logger.info("   2. Configuration drift")
            logger.info("   3. External service issues")
        
        # Save detailed results
        self.diagnosis_results['summary'] = {
            'timestamp': datetime.now().isoformat(),
            'passed': passed,
            'failed': failed,
            'inconclusive': inconclusive,
            'regression_detected': failed > 0
        }
        
        logger.info(f"\n📄 Detailed results saved to diagnosis_results")
        return self.diagnosis_results


async def main():
    """Main diagnostic execution"""
    diagnostic = EnterpriseRegressionDiagnostic()
    
    try:
        results = await diagnostic.run_comprehensive_diagnosis()
        
        # Print final summary
        print("\n" + "=" * 70)
        print("🎯 ENTERPRISE REGRESSION DIAGNOSIS COMPLETE")
        print("=" * 70)
        
        if diagnostic.diagnosis_results.get('summary', {}).get('regression_detected', False):
            print("🚨 REGRESSION DETECTED - Enterprise architecture needs alignment")
            print("📋 Next steps: Run apply_enterprise_alignment.py")
        else:
            print("✅ NO MAJOR REGRESSION - Enterprise architecture stable")
            print("📋 Cache issues may require specific investigation")
        
        return diagnostic.diagnosis_results
        
    except Exception as e:
        logger.error(f"❌ Diagnostic execution failed: {e}")
        return None


if __name__ == "__main__":
    print("🔬 Enterprise Regression Diagnostic Script")
    print("=" * 45)
    print("Purpose: Diagnose post-migration enterprise architecture issues")
    print("Expected: Identify ProductCache instance confusion or Redis issues")
    print("")
    
    # Run diagnosis
    results = asyncio.run(main())
    
    if results:
        print("\n📊 Diagnosis completed successfully")
        print("Check logs above for detailed analysis")
    else:
        print("\n❌ Diagnosis failed - check error logs")
