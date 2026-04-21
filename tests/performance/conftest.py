"""
Configuración de fixtures para performance tests.

✅ REFACTORIZADO (12 Feb 2026): Reutiliza fixtures existentes mediante pytest_plugins.

Este archivo es muy simple porque reutiliza toda la infraestructura existente:
- tests/conftest.py (fixtures principales)
- tests/integration/kb/conftest.py (fixtures específicas de KB health)

Author: Senior QA Team
Date: 12 Febrero 2026 (H3 Día 3 - Refactored)
Version: 2.0.0 - Reutilizando infraestructura
"""

import pytest

# ============================================================================
# REUTILIZAR FIXTURES via pytest_plugins
# ============================================================================
# FIXED (12 Feb 2026): Remover tests.conftest para evitar double-registration
#
# Pytest automáticamente carga tests/conftest.py, NO debemos registrarlo manualmente.
# Solo registramos tests/integration/kb/conftest.py porque está en subdirectorio.
#
# Esto importa fixtures de:
# 1. tests/conftest.py (fixtures globales) ← Auto-cargado por pytest
# 2. tests/integration/kb/conftest.py (fixtures KB-specific) ← Registrado aquí

pytest_plugins = [
    "tests.integration.kb.conftest"  # KB health check fixtures
    # ❌ NO incluir "tests.conftest" - causa ValueError: Plugin already registered
]

# ✅ Con esto ya tenemos disponibles:
# - kb_test_client (de tests/integration/kb/conftest.py)
# - mock_db_pool_health_check (de tests/integration/kb/conftest.py)
# - mock_redis_health_check (de tests/integration/kb/conftest.py)
# - mock_shopify_health_check (de tests/integration/kb/conftest.py)
# - sample_health_response (de tests/integration/kb/conftest.py)
# - mock_degraded_redis (de tests/integration/kb/conftest.py)
# - mock_unhealthy_db (de tests/integration/kb/conftest.py)
# - Y todas las fixtures globales de tests/conftest.py (auto-cargadas)

# No necesitamos duplicar nada más!