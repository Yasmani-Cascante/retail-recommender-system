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
║    SHOPIFY_WEBHOOK_SECRET en .env debe coincidir con el "Signing         ║
║    secret" que se muestra en Shopify Admin → Settings → Notifications    ║
║    → Webhooks. El valor LARGO (64 hex chars) es el correcto.             ║
║    Ejemplo: 141957c71dfef46962b1a2ffa96f1041f5b70607b78c2f168f7000d...  ║
║                                                                          ║
║  POR QUÉ hmac.compare_digest y no ==:                                   ║
║    El operador == en Python hace comparación caracter a caracter y       ║
║    sale en el primer mismatch. Esto permite a un atacante medir el       ║
║    tiempo de respuesta y adivinar la firma bit a bit (timing attack).   ║
║    compare_digest compara en tiempo constante, eliminando esa ventana.  ║
║                                                                          ║
║  FIX 02/05/2026 — strip() defensivo en el secreto:                      ║
║    GCP Secret Manager guarda el secreto tal como fue creado.            ║
║    Si se creó con `echo "secret" | gcloud secrets create`, el `echo`   ║
║    añade un \n al final. Cloud Run inyecta ese \n en la env var.        ║
║    El .strip() elimina cualquier whitespace/newline del secreto antes   ║
║    de usarlo, haciéndolo robusto independientemente de cómo fue         ║
║    almacenado en Secret Manager.                                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import hmac
import hashlib
import base64


def validate_shopify_webhook(
    payload_bytes: bytes,
    shopify_hmac_header: str,
    webhook_secret: str,
) -> bool:
    """
    Valida la firma HMAC-SHA256 del webhook de Shopify.

    Shopify firma cada webhook con:
        HMAC = base64( HMAC-SHA256( key=secret, msg=payload_bytes ) )

    El header enviado por Shopify es: X-Shopify-Hmac-Sha256

    IMPORTANTE — por qué .strip() en el secreto:
        GCP Secret Manager preserva el contenido exacto del secreto,
        incluyendo newlines finales si se creó con `echo "..." | gcloud`.
        Cloud Run inyecta ese valor en la env var con el \n incluido.
        `.strip()` hace la validación robusta sin importar cómo se almacenó.

    IMPORTANTE — por qué RAW bytes del body:
        La validación DEBE hacerse sobre los bytes exactos que Shopify firmó.
        Si se hace json.loads() + json.dumps() antes, el re-serializado puede
        diferir en espacios/orden de claves y la firma no coincidirá.

    Args:
        payload_bytes:        Body raw del request (bytes, sin parsear).
        shopify_hmac_header:  Valor del header X-Shopify-Hmac-Sha256.
        webhook_secret:       Secreto configurado en Shopify (SHOPIFY_WEBHOOK_SECRET).
                              Se aplica .strip() internamente para tolerar \n finales.

    Returns:
        True si la firma es válida, False en caso contrario.

    Ejemplo de uso en router:
        if not validate_shopify_webhook(body_bytes, hmac_header, settings.SHOPIFY_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")
    """
    # .strip() elimina \n, \r, espacios — hace la función robusta ante
    # secretos almacenados en GCP Secret Manager con newline al final.
    secret_bytes = webhook_secret.strip().encode("utf-8")

    computed = base64.b64encode(
        hmac.new(
            secret_bytes,
            payload_bytes,
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    # compare_digest: comparación en tiempo constante.
    # El operador == sale en el primer mismatch → timing attack vector.
    # compare_digest siempre evalúa todos los bytes → tiempo constante.
    return hmac.compare_digest(computed, shopify_hmac_header)
