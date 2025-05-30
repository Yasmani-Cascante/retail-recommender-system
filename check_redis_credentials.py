#!/usr/bin/env python3
"""
Script de verificación rápida de Redis Labs.
Versión simplificada para confirmar que lee las credenciales correctas.
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv('.env.secrets')
load_dotenv('.env')  # Esto sobrescribe las anteriores

print("🔍 Verificación rápida de credenciales de Redis")
print("=" * 50)

# Mostrar credenciales que se están leyendo
redis_host = os.getenv("REDIS_HOST", "NO_CONFIGURADO")
redis_port = os.getenv("REDIS_PORT", "NO_CONFIGURADO")
redis_ssl = os.getenv("REDIS_SSL", "NO_CONFIGURADO")
redis_username = os.getenv("REDIS_USERNAME", "NO_CONFIGURADO")
redis_password = os.getenv("REDIS_PASSWORD", "NO_CONFIGURADO")

print(f"REDIS_HOST: {redis_host}")
print(f"REDIS_PORT: {redis_port}")
print(f"REDIS_SSL: {redis_ssl}")
print(f"REDIS_USERNAME: {redis_username}")
print(f"REDIS_PASSWORD: {'*' * len(redis_password) if redis_password else 'NO_CONFIGURADO'}")

# Verificar si son las credenciales correctas de Redis Labs
if "redis-" in redis_host and redis_port == "14272":
    print("\n✅ Credenciales de Redis Labs detectadas correctamente")
else:
    print("\n❌ Credenciales incorrectas - debería ser Redis Labs")
    print("   Host esperado: redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com")
    print("   Puerto esperado: 14272")
