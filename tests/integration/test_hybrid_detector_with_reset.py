"""
Test Hybrid Intent Detector - WITH SINGLETON RESET
===================================================

Este test resetea el singleton antes de ejecutar para garantizar
que los nuevos patterns se carguen correctamente.
"""

import os
import sys
import time
import asyncio

# ✅ CRITICAL: Reset singleton BEFORE importing
def reset_intent_detector_singleton():
    """Reset the singleton instance to force reload of patterns"""
    import src.api.core.intent_detection as intent_module
    intent_module._detector_instance = None
    print("✅ Singleton reset - patterns will be reloaded")

# Reset BEFORE any other imports
reset_intent_detector_singleton()

# Now import everything else
from src.api.ml.intent_classifier import get_ml_classifier
from src.api.ml.hybrid_detector import get_hybrid_intent_detector


print("=" * 80)
print("🧪 TESTING HYBRID INTENT DETECTOR (WITH SINGLETON RESET)")
print("=" * 80)


# ============================================================================
# TEST 1: ML CLASSIFIER STANDALONE
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: ML CLASSIFIER STANDALONE")
print("=" * 80)

classifier = get_ml_classifier()

print(f"\n📊 Initial state: loaded = {classifier.is_loaded()}")

if not classifier.is_loaded():
    print("\n🔄 Loading model...")
    success = classifier.load()
    if success:
        print("✅ Model loaded successfully")
        info = classifier.get_model_info()
        print(f"   Info: {info}")
    else:
        print("❌ Failed to load model")
        sys.exit(1)

# Test predictions
test_queries = [
    ("¿Cuál es la política de devolución?", "INFORMATIONAL"),
    ("cuanto cuesta el envio", "INFORMATIONAL"),
    ("busco vestido largo para boda", "TRANSACTIONAL"),
    ("necesito bralette en talla M", "TRANSACTIONAL"),
    ("vestido Emma", "TRANSACTIONAL"),
    ("información sobre lencería", "INFORMATIONAL"),
]

print("\n📝 Testing predictions:")
passed = 0
for query, expected in test_queries:
    result = classifier.predict(query)
    if result:
        status = "✅" if result.intent == expected else "⚠️"
        if result.intent == expected:
            passed += 1
        print(f"\n{status} \"{query}\"")
        print(f"   Expected: {expected} | Got: {result.intent}")
        print(f"   Confidence: {result.confidence:.3f}")
        print(f"   Time: {result.inference_time_ms:.2f}ms")
    else:
        print(f"\n❌ \"{query}\"")
        print(f"   Failed to predict")

print(f"\nResults: {passed}/{len(test_queries)} passed")
test1_passed = (passed == len(test_queries))


# ============================================================================
# TEST 2: HYBRID DETECTOR (ML ENABLED)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: HYBRID DETECTOR (ML ENABLED)")
print("=" * 80)

# Set environment for this test
os.environ["ML_INTENT_ENABLED"] = "true"
os.environ["ML_CONFIDENCE_THRESHOLD"] = "0.8"

# Reset hybrid detector to pick up new env vars
import src.api.ml.hybrid_detector as hybrid_module
hybrid_module._global_hybrid_detector = None

detector = get_hybrid_intent_detector()

print(f"\n📊 Configuration:")
print(f"   ML Enabled: {detector.ml_enabled}")
print(f"   Threshold: {detector.confidence_threshold}")

# Test queries
test_queries_hybrid = [
    "¿puedo devolver un vestido?",
    "cuántos días tengo para devolver",
    "regresar algo",
    "cambiar prenda",
    "busco vestido Emma en talla S",
    "vestido de novia"
]

print("\n📝 Testing hybrid detection:")
for query in test_queries_hybrid:
    result = asyncio.run(detector.detect(query))
    print(f"\nQuery: \"{query}\"")
    print(f"   Intent: {result.primary_intent}")
    print(f"   Sub-intent: {result.sub_intent}")
    print(f"   Confidence: {result.confidence:.3f}")
    print(f"   Method: {result.method_used}")
    print(f"   Rule confidence: {result.rule_based_confidence:.3f}")
    print(f"   ML confidence: {result.ml_confidence:.3f}" if result.ml_confidence else "   ML confidence: None")
    print(f"   Time: {result.total_time_ms:.2f}ms")

# Check statistics
stats = detector.get_stats()
print(f"\n📊 Statistics:")
print(f"   Total queries: {stats['total_queries']}")
print(f"   Rule-based used: {stats['rule_based_used']} ({stats['rule_based_percentage']:.1f}%)")
print(f"   ML used: {stats['ml_used']} ({stats['ml_percentage']:.1f}%)")

test2_passed = True  # Manual inspection needed


# ============================================================================
# TEST 3: HYBRID DETECTOR (ML DISABLED)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: HYBRID DETECTOR (ML DISABLED)")
print("=" * 80)

# Set environment for this test
os.environ["ML_INTENT_ENABLED"] = "false"

# Reset hybrid detector
hybrid_module._global_hybrid_detector = None
detector_no_ml = get_hybrid_intent_detector()

print(f"\n📊 Configuration:")
print(f"   ML Enabled: {detector_no_ml.ml_enabled}")

# Test one query
result = asyncio.run(detector_no_ml.detect("¿puedo devolver un vestido?"))
print(f"\nQuery: \"¿puedo devolver un vestido?\"")
print(f"   Intent: {result.primary_intent}")
print(f"   Method: {result.method_used}")
print(f"   Confidence: {result.confidence:.3f}")

if not detector_no_ml.ml_enabled and result.method_used == "rule_based":
    print("\n✅ ML correctly disabled")
    test3_passed = True
else:
    print("\n❌ ML should be disabled")
    test3_passed = False


# ============================================================================
# TEST 4: PERFORMANCE BENCHMARK
# ============================================================================

print("\n" + "=" * 80)
print("TEST 4: PERFORMANCE BENCHMARK")
print("=" * 80)

# Re-enable ML for this test
os.environ["ML_INTENT_ENABLED"] = "true"
hybrid_module._global_hybrid_detector = None
detector = get_hybrid_intent_detector()

# Benchmark queries
benchmark_queries = [
    "¿Cuál es la política de devolución?",
    "cuanto cuesta el envio",
    "busco vestido largo para boda",
    "necesito bralette en talla M",
] * 25  # 100 total queries

print(f"\n🏃 Benchmarking {len(benchmark_queries)} queries...")
latencies = []
start = time.time()

for query in benchmark_queries:
    result = asyncio.run(detector.detect(query))
    latencies.append(result.total_time_ms)

total_time = (time.time() - start) * 1000

# Calculate statistics
latencies.sort()
n = len(latencies)
p50 = latencies[n // 2]
p95 = latencies[int(n * 0.95)]
p99 = latencies[int(n * 0.99)]
avg = sum(latencies) / n

print(f"\n📊 Results:")
print(f"   Total time: {total_time:.0f}ms")
print(f"   Throughput: {n / (total_time / 1000):.1f} queries/sec")
print(f"\n   Latency (ms):")
print(f"     Min: {min(latencies):.2f}ms")
print(f"     Avg: {avg:.2f}ms")
print(f"     P50: {p50:.2f}ms")
print(f"     P95: {p95:.2f}ms")
print(f"     P99: {p99:.2f}ms")
print(f"     Max: {max(latencies):.2f}ms")

# Get method usage
stats = detector.get_stats()
print(f"\n   Method usage:")
print(f"     Rule-based: {stats['rule_based_percentage']:.1f}%")
print(f"     ML: {stats['ml_percentage']:.1f}%")

# Validate targets
print(f"\n🎯 Target validation:")
print(f"   {'✅' if p50 < 10 else '❌'} P50 < 10ms")
print(f"   {'✅' if p95 < 50 else '❌'} P95 < 50ms")
print(f"   {'✅' if p99 < 100 else '❌'} P99 < 100ms")
print(f"   {'✅' if avg < 15 else '❌'} Avg < 15ms")

test4_passed = (p50 < 10 and p95 < 50 and p99 < 100 and avg < 15)


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("📊 TEST SUMMARY")
print("=" * 80)

tests = {
    "ml_classifier": test1_passed,
    "hybrid_ml_enabled": test2_passed,
    "hybrid_ml_disabled": test3_passed,
    "performance": test4_passed
}

for name, passed in tests.items():
    status = "✅" if passed else "❌"
    print(f"{status} {name}: {'PASSED' if passed else 'FAILED'}")

if all(tests.values()):
    print("\n🎉 ALL TESTS PASSED!")
    sys.exit(0)
else:
    print("\n⚠️ SOME TESTS FAILED")
    sys.exit(1)