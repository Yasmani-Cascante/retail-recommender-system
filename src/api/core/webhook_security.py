"""
webhook_security.py — Validación HMAC para Webhooks de Shopify
================================================================

╔══════════════════════════════════════════════════════════════════════════╗
║  NOTA PARA DESARROLLADORES — ESTADO ACTUAL (Feb 2026)                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Módulo utilitario PURO — sin dependencias de FastAPI ni de la app.     ║
║  Es usado por webhooks_router.py para validar la firma de cada          ║
║  request entrante de Shopify antes de procesar el payload.              ║
║                                                                          ║
║  ESTADO: ACTIVO Y EN USO.                                               ║
║    - translations/update llega activamente y pasa por esta validación.  ║
║    - Si Shopify agrega pages/* en el futuro, este módulo ya los         ║
║      valida sin cambio alguno (es genérico por diseño).                  ║
║                                                                          ║
║  CONFIGURACIÓN REQUERIDA:                                               ║
║    SHOPIFY_WEBHOOK_SECRET en .env debe coincidir con el “Signing         ║
║    secret” que se muestra en Shopify Admin → Settings → Notifications    ║
║    → Webhooks. El valor LARGO (64 hex chars) es el correcto.             ║
║    Ejemplo: 141957c71dfef46962b1a2ffa96f1041f5b70607b78c2f168f7000d...  ║
║                                                                          ║
║  POR QUÉ hmac.compare_digest y no ==:                                   ║
║    El operador == en Python hace comparación caracter a caracter y       ║
║    sale en el primer mismatch. Esto permite a un atacante medir el       ║
║    tiempo de respuesta y adivinar la firma bit a bit (timing attack).   ║
║    compare_digest compara en tiempo constante, eliminando esa ventana.  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import hmac
import hashlib
import base64
from typing import Optional

def validate_shopify_webhook(
    payload_bytes: bytes,
    shopify_hmac_header: str,
    webhook_secret: str,
) -> bool:
    """
    Valida la firma HMAC-SHA256 del webhook de Shopify.
    
    Shopify firma cada webhook con:
      HMAC = base64(SHA256(payload, secret))
    
    El header es: X-Shopify-Hmac-Sha256
    
    IMPORTANTE:
    - La validación DEBE hacerse sobre los bytes RAW del body,
      antes de cualquier parsing JSON.
    - Usar hmac.compare_digest() para comparación segura
      (previene timing attacks).
    
    Args:
        payload_bytes: Body raw del request (bytes, no str)
        shopify_hmac_header: Valor del header X-Shopify-Hmac-Sha256
        webhook_secret: Secreto configurado en Shopify Partners Dashboard
    
    Returns:
        True si la firma es válida, False en caso contrario
    
    Ejemplo:
        if not validate_shopify_webhook(body, hmac_header, secret):
            raise HTTPException(status_code=401, detail="Invalid HMAC")
    """
    computed = base64.b64encode(
        hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    
    # compare_digest: tiempo constante, no vulnerable a timing attacks
    return hmac.compare_digest(computed, shopify_hmac_header)