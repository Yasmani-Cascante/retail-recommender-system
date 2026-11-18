"""
Mensajes localizados para los modos degradados del chat
=======================================================

R-2 parte 2 + R-4 (17/11/2026). Ver
docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/Evaluacion_Integral_16092026/
DCT_Alineacion_Venv_Diagnostico_Suite_16112026.md

POR QUE EXISTE ESTE MODULO
--------------------------
Antes de este cambio, cada camino degradado del handler tenia su propio texto
fijo, escrito en un momento distinto y en un idioma distinto:

  * Sin respuesta de la base de conocimiento -> el chat buscaba PRODUCTOS para
    una pregunta de politica (y caia al texto provisional de abajo).
  * Texto provisional sin productos -> siempre en espanol (R-4).
  * Respaldo de emergencia -> siempre en ingles y repitiendo la consulta.

Este modulo es la UNICA fuente de esos textos: localizados, revisados y
testeados (tests/unit/test_localized_messages.py).

REGLAS DE DISENO
----------------
1. Solo libreria estandar, sin IO ni red: el handler lo importa a nivel de
   modulo, asi que no puede fallar en el arranque ni durante una caida.
2. Ningun dato inventado: el mensaje honesto NO afirma nada sobre la tienda;
   solo enlaza a la pagina de Shopify de la que se sincroniza la base de
   conocimiento (el mismo texto que el chat muestra cuando todo funciona).
   Shopify sirve esas paginas aunque fallen Supabase, Redis o este servicio.
3. Idioma por defecto: espanol (idioma principal de la tienda), igual que el
   saludo del handler.

MANTENIMIENTO
-------------
* Si se RENOMBRA una pagina en Shopify (cambia su handle), hay que actualizar
  KB_PAGE_HANDLES; si no, el enlace del modo degradado dara 404.
* Si se PUBLICA un idioma nuevo en Translate & Adapt (p. ej. "de"), hay que
  anadirlo a PUBLISHED_STOREFRONT_LOCALES para que el enlace abra la pagina
  traducida en lugar de la espanola.
"""

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Idiomas
# ---------------------------------------------------------------------------

#: Idioma principal de la tienda: se usa si el idioma no se reconoce.
DEFAULT_LANGUAGE = "es"

#: Idiomas con textos propios en este modulo.
SUPPORTED_LANGUAGES = ("es", "en", "fr", "de", "it")

#: Idiomas NO principales publicados en la tienda Shopify (comprobado el
#: 17/11/2026 con `shopLocales`: es principal; en y fr publicados).
#: Shopify sirve sus paginas con prefijo de idioma (/en/pages/..., /fr/pages/...).
#: Un idioma que no este aqui (de, it) abre la pagina en el idioma principal,
#: SIN prefijo: un prefijo de un idioma no publicado no sirve la pagina.
PUBLISHED_STOREFRONT_LOCALES = ("en", "fr")


def normalize_language(language: Optional[str]) -> str:
    """
    Normaliza un codigo de idioma a uno de SUPPORTED_LANGUAGES.

    Ejemplos:
        "en-US" -> "en";  "FR" -> "fr";  None -> "es";  "pt" -> "es"
    """
    if not language or not isinstance(language, str):
        return DEFAULT_LANGUAGE
    # "en-US" / "en_US" -> "en"
    primary = language.strip().replace("_", "-").split("-")[0].lower()
    return primary if primary in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Paginas de la base de conocimiento en Shopify
# ---------------------------------------------------------------------------

#: Tema (InformationalSubIntent.value) -> handle de la pagina de Shopify de la
#: que se sincroniza `kb_contents`. Handles leidos de la API de Shopify el
#: 17/11/2026 (`pages { title handle }`). Cubre los 13 temas del enum.
KB_PAGE_HANDLES = {
    "policy_return": "como-devolver-un-producto",
    "policy_shipping": "como-funcionan-los-envios",
    "policy_payment": "metodos-de-pago",
    "policy_warranty": "garantia-y-defectos",
    "policy_privacy": "politica-de-privacidad-y-proteccion-de-datos",
    "product_material": "guia-de-materiales-y-tejidos",
    "product_sizing": "guia-de-tallas",
    "product_care": "guia-de-cuidado-de-productos",
    "product_availability": "disponibilidad-de-productos",
    "account_orders": "donde-esta-mi-pedido",
    "account_modifications": "cancelaciones-y-modificaciones-de-pedidos",
    "general_faq": "preguntas-frecuentes-faq",
    "unknown": "preguntas-frecuentes-faq",
}

#: Pagina para cualquier tema no listado (nunca deberia ocurrir con el enum
#: actual, pero un tema nuevo sin pagina no debe romper el mensaje).
DEFAULT_KB_PAGE_HANDLE = "preguntas-frecuentes-faq"

#: Texto del enlace, por tema y por idioma (sustantivos cortos, no titulos).
KB_PAGE_TITLES = {
    "como-devolver-un-producto": {
        "es": "Devoluciones", "en": "Returns", "fr": "Retours",
        "de": "Rücksendungen", "it": "Resi",
    },
    "como-funcionan-los-envios": {
        "es": "Envíos", "en": "Shipping", "fr": "Livraison",
        "de": "Versand", "it": "Spedizioni",
    },
    "metodos-de-pago": {
        "es": "Métodos de pago", "en": "Payment methods", "fr": "Moyens de paiement",
        "de": "Zahlungsmethoden", "it": "Metodi di pagamento",
    },
    "garantia-y-defectos": {
        "es": "Garantía y defectos", "en": "Warranty and defects",
        "fr": "Garantie et défauts", "de": "Garantie und Mängel",
        "it": "Garanzia e difetti",
    },
    "politica-de-privacidad-y-proteccion-de-datos": {
        "es": "Privacidad y protección de datos", "en": "Privacy and data protection",
        "fr": "Confidentialité et protection des données", "de": "Datenschutz",
        "it": "Privacy e protezione dei dati",
    },
    "guia-de-materiales-y-tejidos": {
        "es": "Materiales y tejidos", "en": "Materials and fabrics",
        "fr": "Matières et tissus", "de": "Materialien und Stoffe",
        "it": "Materiali e tessuti",
    },
    "guia-de-tallas": {
        "es": "Guía de tallas", "en": "Size guide", "fr": "Guide des tailles",
        "de": "Größentabelle", "it": "Guida alle taglie",
    },
    "guia-de-cuidado-de-productos": {
        "es": "Cuidado de los productos", "en": "Product care",
        "fr": "Entretien des produits", "de": "Produktpflege",
        "it": "Cura dei prodotti",
    },
    "disponibilidad-de-productos": {
        "es": "Disponibilidad de productos", "en": "Product availability",
        "fr": "Disponibilité des produits", "de": "Produktverfügbarkeit",
        "it": "Disponibilità dei prodotti",
    },
    "donde-esta-mi-pedido": {
        "es": "Seguimiento de pedidos", "en": "Order tracking",
        "fr": "Suivi de commande", "de": "Sendungsverfolgung",
        "it": "Tracciamento dell'ordine",
    },
    "cancelaciones-y-modificaciones-de-pedidos": {
        "es": "Cancelaciones y modificaciones de pedidos",
        "en": "Order cancellations and changes",
        "fr": "Annulation et modification de commande",
        "de": "Stornierung und Änderung von Bestellungen",
        "it": "Annullamento e modifica degli ordini",
    },
    "preguntas-frecuentes-faq": {
        "es": "Preguntas frecuentes", "en": "FAQ", "fr": "Questions fréquentes",
        "de": "Häufige Fragen", "it": "Domande frequenti",
    },
}


def _sub_intent_value(sub_intent: Any) -> str:
    """Acepta el enum InformationalSubIntent o su valor en texto."""
    value = getattr(sub_intent, "value", sub_intent)
    return str(value).strip().lower() if value is not None else ""


def kb_page_handle(sub_intent: Any) -> str:
    """Handle de la pagina de Shopify para un tema (o la de preguntas frecuentes)."""
    return KB_PAGE_HANDLES.get(_sub_intent_value(sub_intent), DEFAULT_KB_PAGE_HANDLE)


def kb_page_url(sub_intent: Any, language: Optional[str]) -> str:
    """
    URL RELATIVA de la pagina de la base de conocimiento en la tienda.

    Es relativa a proposito: el widget vive dentro de la tienda, asi que el
    navegador la resuelve contra el dominio de la tienda (sin codificar aqui
    el dominio, que cambiara al pasar de *.myshopify.com a un dominio propio).

    Ejemplos:
        ("policy_return", "en") -> "/en/pages/como-devolver-un-producto"
        ("policy_return", "es") -> "/pages/como-devolver-un-producto"
        ("policy_return", "de") -> "/pages/como-devolver-un-producto"  (de no publicado)
    """
    lang = normalize_language(language)
    prefix = f"/{lang}" if lang in PUBLISHED_STOREFRONT_LOCALES else ""
    return f"{prefix}/pages/{kb_page_handle(sub_intent)}"


def kb_page_title(sub_intent: Any, language: Optional[str]) -> str:
    """Texto del enlace en el idioma del cliente."""
    titles = KB_PAGE_TITLES.get(kb_page_handle(sub_intent), KB_PAGE_TITLES[DEFAULT_KB_PAGE_HANDLE])
    return titles[normalize_language(language)]


# ---------------------------------------------------------------------------
# Textos (aprobados por Yasmani el 17/11/2026)
# ---------------------------------------------------------------------------

_KB_UNAVAILABLE_TEMPLATES = {
    "es": ("Ahora mismo no puedo consultar esa información. Puedes verla en "
           "[{title}]({url}) o volver a preguntarme en unos minutos."),
    "en": ("I can't access that information right now. You can find it in "
           "[{title}]({url}) or ask me again in a few minutes."),
    "fr": ("Je ne peux pas consulter cette information pour le moment. Vous la "
           "trouverez ici : [{title}]({url}), ou reposez-moi la question dans "
           "quelques minutes."),
    "de": ("Ich kann diese Information gerade nicht abrufen. Sie finden sie unter "
           "[{title}]({url}), oder fragen Sie mich in ein paar Minuten noch einmal."),
    "it": ("In questo momento non riesco a consultare questa informazione. Puoi "
           "trovarla qui: [{title}]({url}), oppure chiedimelo di nuovo tra qualche "
           "minuto."),
}

_NO_PRODUCTS_TEMPLATES = {
    "es": "No he encontrado productos para esta búsqueda. ¿Quieres que te muestre otra cosa?",
    "en": "I couldn't find any products for this search. Would you like me to show you something else?",
    "fr": "Je n'ai trouvé aucun produit pour cette recherche. Voulez-vous que je vous montre autre chose ?",
    "de": "Ich habe für diese Suche keine Produkte gefunden. Soll ich Ihnen etwas anderes zeigen?",
    "it": "Non ho trovato prodotti per questa ricerca. Vuoi che ti mostri qualcos'altro?",
}

_SOME_PRODUCTS_TEMPLATES = {
    "es": "Aquí tienes algunas opciones que pueden encajar.",
    "en": "Here are some options that might suit you.",
    "fr": "Voici quelques options qui pourraient vous convenir.",
    "de": "Hier sind einige Optionen, die passen könnten.",
    "it": "Ecco alcune opzioni che potrebbero fare al caso tuo.",
}

_EMERGENCY_TEMPLATES = {
    "es": "Lo siento, ha ocurrido un problema al procesar tu mensaje. ¿Puedes intentarlo de nuevo?",
    "en": "Sorry, something went wrong while processing your message. Could you try again?",
    "fr": "Désolé, un problème est survenu lors du traitement de votre message. Pouvez-vous réessayer ?",
    "de": "Entschuldigung, bei der Verarbeitung Ihrer Nachricht ist ein Problem aufgetreten. Können Sie es noch einmal versuchen?",
    "it": "Mi dispiace, si è verificato un problema durante l'elaborazione del tuo messaggio. Puoi riprovare?",
}


def kb_unavailable_message(language: Optional[str], sub_intent: Any) -> str:
    """
    Mensaje honesto cuando la base de conocimiento no puede responder
    (sin instancia, sin respuesta o con error). Enlaza a la pagina de Shopify
    del tema, en el idioma del cliente si la tienda lo tiene publicado.
    """
    lang = normalize_language(language)
    return _KB_UNAVAILABLE_TEMPLATES[lang].format(
        title=kb_page_title(sub_intent, lang),
        url=kb_page_url(sub_intent, lang),
    )


def no_products_placeholder(language: Optional[str], has_products: bool) -> str:
    """
    Texto provisional de la respuesta de productos (R-4). Solo llega al usuario
    si la personalizacion no lo sobrescribe; por eso debe estar en su idioma.
    """
    templates = _SOME_PRODUCTS_TEMPLATES if has_products else _NO_PRODUCTS_TEMPLATES
    return templates[normalize_language(language)]


def emergency_message(language: Optional[str]) -> str:
    """
    Texto del respaldo de emergencia del handler. A diferencia del anterior,
    NO repite la consulta del usuario (no se refleja texto no confiable).
    """
    return _EMERGENCY_TEMPLATES[normalize_language(language)]
