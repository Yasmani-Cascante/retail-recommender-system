"""
Load Testing Suite - Knowledge Base Multi-Language
===================================================

Valida performance del sistema bajo carga concurrente.

Requirements:
    pip install locust

Usage:
    # Web UI (recommended)
    locust -f tests/performance/locustfile_kb.py --host=http://localhost:8000
    # Open http://localhost:8089

    # Headless
    locust -f tests/performance/locustfile_kb.py --host=http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 5m --headless

Author: Retail Recommender System Team
Date: 2026-01-24
Version: 1.0.0
"""

from locust import HttpUser, task, between
import random


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

# All valid sub_intents
SUB_INTENTS = [
    "policy_return",
    "policy_shipping",
    "policy_warranty",
    "policy_payment",
    "policy_privacy",
    "product_care",
    "product_sizing",
    "product_material",
    "product_availability",
    "account_modifications",
    "account_orders",
    "general_faq",
    "unknown"
]

# Supported languages
LANGUAGES = ["es", "en"]

# Accept-Language headers to simulate real traffic
ACCEPT_LANGUAGE_HEADERS = [
    "en-US,en;q=0.9,es;q=0.8",      # 40% - English preference
    "es-ES,es;q=0.9,en;q=0.8",      # 40% - Spanish preference
    "es-MX,es;q=0.9",               # 10% - Spanish only
    "en-GB,en;q=0.9",               # 10% - English only
]


# ══════════════════════════════════════════════════════════════════════════
# USER BEHAVIOR
# ══════════════════════════════════════════════════════════════════════════

class KBUser(HttpUser):
    """
    Simulates user behavior hitting KB API.
    
    Scenarios:
    1. Random KB queries (80% of traffic)
    2. Repeated queries (15% - tests cache)
    3. Invalid requests (5% - tests error handling)
    """
    
    # Wait time between requests (seconds)
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when user starts."""
        # Pick a random Accept-Language header for this user's session
        self.accept_language = random.choice(ACCEPT_LANGUAGE_HEADERS)
    
    @task(80)
    def get_kb_answer_random(self):
        """
        Task: Random KB query (80% weight).
        
        Simulates typical user querying different sub_intents.
        """
        sub_intent = random.choice(SUB_INTENTS)
        language = random.choice(LANGUAGES)
        
        # 50% use explicit language, 50% rely on Accept-Language
        if random.random() < 0.5:
            # Explicit language parameter
            self.client.get(
                f"/api/v1/kb/answer?sub_intent={sub_intent}&language={language}",
                name="/api/v1/kb/answer [explicit]"
            )
        else:
            # Accept-Language header
            self.client.get(
                f"/api/v1/kb/answer?sub_intent={sub_intent}",
                headers={"Accept-Language": self.accept_language},
                name="/api/v1/kb/answer [header]"
            )
    
    @task(15)
    def get_kb_answer_repeated(self):
        """
        Task: Repeated query (15% weight).
        
        Tests cache performance by querying same content.
        """
        # Always query popular sub_intent
        popular = random.choice(["policy_return", "policy_shipping", "product_care"])
        
        self.client.get(
            f"/api/v1/kb/answer?sub_intent={popular}&language=es",
            name="/api/v1/kb/answer [cached]"
        )
    
    @task(5)
    def get_kb_answer_invalid(self):
        """
        Task: Invalid request (5% weight).
        
        Tests error handling.
        """
        # Invalid sub_intent
        self.client.get(
            "/api/v1/kb/answer?sub_intent=invalid_xyz&language=es",
            name="/api/v1/kb/answer [invalid]"
        )


class KBHealthCheckUser(HttpUser):
    """
    Simulates periodic health checks.
    
    Lower frequency, just monitoring.
    """
    
    wait_time = between(5, 10)
    
    @task
    def health_check(self):
        """Check API health."""
        self.client.get("/api/v1/kb/health", name="/api/v1/kb/health")


# ══════════════════════════════════════════════════════════════════════════
# ADVANCED SCENARIOS (Optional)
# ══════════════════════════════════════════════════════════════════════════

class KBPowerUser(HttpUser):
    """
    Simulates power user with sequential queries.
    
    Uncomment to enable this user type.
    """
    
    wait_time = between(0.5, 1.5)
    
    @task
    def sequential_queries(self):
        """
        Sequential KB queries simulating user browsing.
        """
        # User browses multiple policies
        policies = ["policy_return", "policy_shipping", "policy_warranty"]
        
        for policy in policies:
            self.client.get(
                f"/api/v1/kb/answer?sub_intent={policy}&language=en",
                name="/api/v1/kb/answer [sequential]"
            )
            # Small wait between queries
            self.wait()


# ══════════════════════════════════════════════════════════════════════════
# CUSTOM EVENTS (for advanced metrics)
# ══════════════════════════════════════════════════════════════════════════

from locust import events

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 70)
    print("LOAD TEST STARTING - KB Multi-Language API")
    print("=" * 70)
    print(f"Target host: {environment.host}")
    print(f"User classes: {[u.__name__ for u in environment.user_classes]}")
    print("=" * 70)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("\n" + "=" * 70)
    print("LOAD TEST COMPLETED")
    print("=" * 70)
    print("Check results above for:")
    print("  - Request count & RPS")
    print("  - Response times (P50, P95, P99)")
    print("  - Failure rate")
    print("  - Cache performance (compare [cached] vs others)")
    print("=" * 70)
