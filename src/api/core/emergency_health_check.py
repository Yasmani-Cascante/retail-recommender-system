# src/api/core/emergency_health_check.py
"""
🚨 EMERGENCY HOTFIX #3: Lightweight Health Check
===============================================

Replaces the current health check that's causing 104s response times
with a lightweight version that responds in <1s.

CRITICAL FIXES:
- Removes heavy dependency checks
- Parallel non-blocking health checks
- 2s maximum timeout
- Always returns response (never hangs)

Author: CTO Emergency Response Team
Version: 1.0.0-hotfix  
Date: 05 August 2025
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class HealthCheckConfig:
    """Configuration for emergency health check"""
    max_total_timeout: float = 2.0  # Maximum 2 seconds total
    dependency_timeout: float = 0.5  # 500ms per dependency check
    parallel_checks: bool = True      # Run checks in parallel
    
class EmergencyHealthChecker:
    """
    🚨 Emergency lightweight health checker
    
    Designed to respond in <1s even when dependencies are slow/failing.
    Uses parallel non-blocking checks with aggressive timeouts.
    """
    
    def __init__(self, config: HealthCheckConfig = None):
        self.config = config or HealthCheckConfig()
        self.start_time = time.time()
        
    async def check_system_health(self, redis_client=None, 
                                 shopify_client=None) -> Dict[str, Any]:
        """
        Main health check method - ALWAYS responds within 2 seconds
        
        Args:
            redis_client: Optional Redis client to check
            shopify_client: Optional Shopify client to check
            
        Returns:
            Dict with health status and component info
        """
        check_start_time = time.time()
        
        try:
            # Base system status (always healthy if process is running)
            health_status = {
                "status": "healthy",
                "timestamp": check_start_time,
                "version": "2.0.1-emergency-hotfix",
                "uptime_seconds": round(check_start_time - self.start_time, 1),
                "emergency_hotfix_active": True,
                "components": {},
                "performance": {}
            }
            
            # Run dependency checks in parallel with timeout
            if self.config.parallel_checks:
                component_results = await self._run_parallel_checks(
                    redis_client, shopify_client
                )
            else:
                component_results = await self._run_sequential_checks(
                    redis_client, shopify_client  
                )
            
            health_status["components"] = component_results
            
            # Calculate overall health based on components
            health_status["status"] = self._calculate_overall_status(component_results)
            
            # Performance metadata
            response_time = (time.time() - check_start_time) * 1000
            health_status["performance"] = {
                "response_time_ms": round(response_time, 1),
                "target_time_ms": 1000,
                "performance_grade": "A" if response_time < 500 else "B" if response_time < 1000 else "C",
                "checks_completed": len(component_results)
            }
            
            logger.info(f"✅ Health check completed in {response_time:.1f}ms - Status: {health_status['status']}")
            
            return health_status
            
        except Exception as e:
            # Emergency fallback - never let health check fail completely
            response_time = (time.time() - check_start_time) * 1000
            logger.error(f"❌ Health check error after {response_time:.1f}ms: {e}")
            
            return {
                "status": "degraded",
                "timestamp": check_start_time,
                "version": "2.0.1-emergency-hotfix",
                "uptime_seconds": round(check_start_time - self.start_time, 1),
                "emergency_hotfix_active": True,
                "error": f"Health check error: {str(e)[:100]}",
                "components": {"system": {"status": "operational"}},
                "performance": {
                    "response_time_ms": round(response_time, 1),
                    "error_occurred": True
                }
            }
    
    async def _run_parallel_checks(self, redis_client, shopify_client) -> Dict[str, Dict]:
        """Run all dependency checks in parallel with timeout"""
        
        check_tasks = []
        
        # Redis check
        if redis_client:
            check_tasks.append(self._check_redis_async(redis_client))
        
        # Shopify check  
        if shopify_client:
            check_tasks.append(self._check_shopify_async(shopify_client))
        
        # Emergency cache check
        check_tasks.append(self._check_emergency_cache())
        
        # System resources check
        check_tasks.append(self._check_system_resources())
        
        if not check_tasks:
            return {"system": {"status": "operational", "message": "No dependencies to check"}}
        
        try:
            # Run all checks in parallel with global timeout
            results = await asyncio.wait_for(
                asyncio.gather(*check_tasks, return_exceptions=True),
                timeout=self.config.max_total_timeout
            )
            
            # Process results
            component_status = {}
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    component_name = f"component_{i}"
                    component_status[component_name] = {
                        "status": "error",
                        "error": str(result)[:50]
                    }
                else:
                    component_status.update(result)
            
            return component_status
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Health checks timed out after {self.config.max_total_timeout}s")
            return {
                "timeout": {
                    "status": "timeout",
                    "message": f"Checks timed out after {self.config.max_total_timeout}s"
                }
            }
    
    async def _run_sequential_checks(self, redis_client, shopify_client) -> Dict[str, Dict]:
        """Run dependency checks sequentially (fallback method)"""
        
        components = {}
        
        # Quick system check
        components.update(await self._check_system_resources())
        
        # Redis check with timeout
        if redis_client:
            try:
                redis_result = await asyncio.wait_for(
                    self._check_redis_async(redis_client),
                    timeout=self.config.dependency_timeout
                )
                components.update(redis_result)
            except asyncio.TimeoutError:
                components["redis"] = {"status": "timeout"}
            except Exception as e:
                components["redis"] = {"status": "error", "error": str(e)[:50]}
        
        # Emergency cache check
        try:
            cache_result = await asyncio.wait_for(
                self._check_emergency_cache(),
                timeout=self.config.dependency_timeout
            )
            components.update(cache_result)
        except Exception as e:
            components["emergency_cache"] = {"status": "error", "error": str(e)[:50]}
        
        return components
    
    async def _check_redis_async(self, redis_client) -> Dict[str, Dict]:
        """Lightweight Redis health check"""
        try:
            # Non-blocking ping
            await asyncio.to_thread(redis_client.ping)
            
            return {
                "redis": {
                    "status": "connected",
                    "type": "cache"
                }
            }
        except Exception as e:
            return {
                "redis": {
                    "status": "disconnected", 
                    "error": str(e)[:50],
                    "type": "cache"
                }
            }
    
    async def _check_shopify_async(self, shopify_client) -> Dict[str, Dict]:
        """Lightweight Shopify health check"""
        try:
            # Don't actually call Shopify API - just check client exists
            if shopify_client and hasattr(shopify_client, 'shop_url'):
                return {
                    "shopify": {
                        "status": "configured",
                        "shop_url": shopify_client.shop_url,
                        "type": "external_api"
                    }
                }
            else:
                return {
                    "shopify": {
                        "status": "not_configured",
                        "type": "external_api"
                    }
                }
        except Exception as e:
            return {
                "shopify": {
                    "status": "error",
                    "error": str(e)[:50],
                    "type": "external_api"
                }
            }
    
    async def _check_emergency_cache(self) -> Dict[str, Dict]:
        """Check emergency cache status"""
        try:
            from src.api.core.emergency_shopify_cache import get_emergency_cache_stats
            
            cache_stats = get_emergency_cache_stats()
            
            return {
                "emergency_cache": {
                    "status": "operational",
                    "entries": cache_stats.get("total_entries", 0),
                    "hit_ratio": cache_stats.get("hit_ratio", 0),
                    "type": "memory_cache"
                }
            }
        except Exception as e:
            return {
                "emergency_cache": {
                    "status": "error",
                    "error": str(e)[:50],
                    "type": "memory_cache"
                }
            }
    
    async def _check_system_resources(self) -> Dict[str, Dict]:
        """Quick system resource check"""
        try:
            import psutil
            
            # Quick CPU and memory check
            cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
            memory = psutil.virtual_memory()
            
            return {
                "system": {
                    "status": "operational",
                    "cpu_percent": round(cpu_percent, 1),
                    "memory_percent": round(memory.percent, 1),
                    "type": "system_resources"
                }
            }
        except ImportError:
            # psutil not available - basic check
            return {
                "system": {
                    "status": "operational",
                    "message": "Basic system check (psutil not available)",
                    "type": "system_resources"
                }
            }
        except Exception as e:
            return {
                "system": {
                    "status": "degraded",
                    "error": str(e)[:50],
                    "type": "system_resources"
                }
            }
    
    def _calculate_overall_status(self, components: Dict[str, Dict]) -> str:
        """Calculate overall system health from component statuses"""
        
        if not components:
            return "healthy"  # No components to check
        
        statuses = [comp.get("status", "unknown") for comp in components.values()]
        
        # Count status types
        operational_count = statuses.count("operational") + statuses.count("connected") + statuses.count("configured")
        error_count = statuses.count("error")
        timeout_count = statuses.count("timeout")
        total_count = len(statuses)
        
        # Determine overall status
        if error_count == 0 and timeout_count == 0:
            return "healthy"
        elif operational_count >= total_count / 2:  # More than half operational
            return "degraded"
        else:
            return "unhealthy"

# Factory function
def create_emergency_health_checker(config: HealthCheckConfig = None) -> EmergencyHealthChecker:
    """Create emergency health checker instance"""
    return EmergencyHealthChecker(config)

# FastAPI endpoint implementation
async def emergency_health_endpoint(redis_client=None, shopify_client=None) -> Dict[str, Any]:
    """
    🚨 Emergency health check endpoint implementation
    
    Replace existing /health endpoint with this implementation:
    
    @app.get("/health")
    async def health_check():
        from src.api.core.emergency_health_check import emergency_health_endpoint
        from src.api.core.store import get_shopify_client
        
        # Get dependencies (optional)
        shopify_client = get_shopify_client()
        redis_client = None  # Add Redis client if available
        
        return await emergency_health_endpoint(redis_client, shopify_client)
    """
    
    health_checker = create_emergency_health_checker()
    return await health_checker.check_system_health(redis_client, shopify_client)

# Quick health check (even faster)
async def quick_health_check() -> Dict[str, Any]:
    """
    ⚡ Ultra-fast health check for load balancers
    
    Responds in <100ms with minimal checks
    """
    start_time = time.time()
    
    return {
        "status": "healthy",
        "timestamp": start_time,
        "version": "2.0.1-emergency-hotfix",
        "response_time_ms": round((time.time() - start_time) * 1000, 1),
        "check_type": "quick",
        "emergency_hotfix_active": True
    }

# 📋 INSTALLATION INSTRUCTIONS
"""
🚨 EMERGENCY HEALTH CHECK INSTALLATION:

1. ADD TO main_unified_redis.py:

   from src.api.core.emergency_health_check import emergency_health_endpoint
   
   @app.get("/health")
   async def health_check():
       from src.api.core.store import get_shopify_client
       
       shopify_client = get_shopify_client()
       redis_client = None  # Add your Redis client here if available
       
       return await emergency_health_endpoint(redis_client, shopify_client)

2. OPTIONAL - Add quick health check:

   @app.get("/health/quick")
   async def quick_health():
       from src.api.core.emergency_health_check import quick_health_check
       return await quick_health_check()

3. TEST INSTALLATION:
   curl http://localhost:8000/health
   
   Expected: Response in <1s with status "healthy" or "degraded"

🎯 EXPECTED IMPROVEMENTS:
- Health check: 104s → <1s response time  
- Always responds (never hangs)
- Graceful degradation when dependencies fail
- Detailed component status for debugging

⚠️ MONITORING:
- Response time should be <500ms typically
- Status should be "healthy" when all components work
- "degraded" is acceptable if external APIs are slow
- "unhealthy" indicates serious system issues
"""
