"""
R-36 (28/11/2026): un saludo al principio ya no se traga la pregunta
=====================================================================

Que protege este fichero
------------------------
1. Un mensaje que es SOLO un saludo sigue siendo GREETING (0,95), como antes:
   "hola", "buenas tardes!", "hola, que tal?", "hey 👋"...
2. Un mensaje que EMPIEZA por un saludo pero trae algo mas ya NO es GREETING: sigue
   la deteccion normal. Antes recibia solo la plantilla de saludo y la pregunta se
   perdia ("buenas, cuanto tarda el envio a mexico?" -> saludo).
3. La regla `is_greeting_only` (que decide "solo saludo") en sus casos limite.

Solo capa de reglas (sin sklearn ni MiniLM): deterministica. La medicion completa con
las tres capas y la capa LLM esta en el DCT (DCT_Fidelidad_Reformulacion_KB_23112026.md,
seccion 7.32): de 345 a 356 de 420 consultas correctas, 0 perdidas.
"""

import pytest

from src.api.core.intent_detection import RuleBasedIntentDetector, is_greeting_only
from src.api.core.intent_types import IntentType


@pytest.fixture(scope="module")
def detector():
    return RuleBasedIntentDetector()


# Mensajes que son SOLO un saludo (es/en, con signos, emojis y cortesias)
GREETING_ONLY = [
    "hola", "hi", "hi!", "hiii", "hola!!", "hey", "hello :)", "hey 👋",
    "buenas", "buenas tardes!", "Buenas noches 🙂", "Hola, buenos días", "hola buenas",
    "hola, qué tal?", "hola que tal", "Hola, ¿cómo estás?", "hola a todos", "saludos",
    "good evening!", "good morning, how are you?", "hi there", "hey guys", "hello everyone!",
]

# Mensajes de los conjuntos de R-32 que empiezan por saludo y traen una pregunta o una compra
# (hasta R-36, todos recibian solo la plantilla de saludo)
GREETING_PLUS_CONTENT = [
    "hola! busco un bolso negro de cuero",
    "hi! looking for a black leather bag",
    "buenas, cuanto tarda el envio a mexico?",
    "hello, how long does shipping to mexico take?",
    "hola, tienen vestidos rojos en talla S?",
    "hey, do you have red dresses in S?",
    "buenas! se me rompio el cierre de la chaqueta, lo cubre la garantia?",
    "hi! the zipper on my jacket broke, is that covered by the warranty?",
    "hola! qué me recomiendan para una boda de día?",
    "hi! what do you recommend for a daytime wedding?",
    "buenas, como saco una mancha de grasa de un pantalon?",
    "hey, how do i get a grease stain out of trousers?",
    "hola!! a las zapas q compre se les despego la suela al mes, me las cambian o q?",
    "hey the sole on my sneakers came off after like a month?? do u replace them or nah",
]


class TestGreetingOnlyStillGreets:

    @pytest.mark.parametrize("query", GREETING_ONLY)
    def test_pure_greeting_is_greeting(self, detector, query):
        result = detector.detect(query)
        assert result.primary_intent == IntentType.GREETING
        assert result.confidence == 0.95
        assert result.sub_intent is None


class TestGreetingNoLongerSwallowsTheMessage:

    @pytest.mark.parametrize("query", GREETING_PLUS_CONTENT)
    def test_greeting_plus_content_is_not_a_greeting(self, detector, query):
        # Con el codigo anterior a R-36 TODOS estos devolvian GREETING 0,95.
        assert detector.detect(query).primary_intent != IntentType.GREETING

    @pytest.mark.parametrize("query, sub_intent", [
        ("buenas, cuanto tarda el envio a mexico?", "policy_shipping"),
        ("hello, how long does shipping to mexico take?", "policy_shipping"),
        ("hola, ¿cuánto tarda el envío?", "policy_shipping"),
    ])
    def test_the_question_reaches_its_topic(self, detector, query, sub_intent):
        # Mismo resultado que la pregunta sin saludo: la regla de envios la reconoce.
        result = detector.detect(query)
        assert (result.primary_intent, result.sub_intent) == (IntentType.INFORMATIONAL, sub_intent)
        assert detector.detect(query.split(",", 1)[1].strip()).sub_intent == sub_intent

    def test_purchase_after_greeting_is_a_purchase(self, detector):
        result = detector.detect("hola! busco un bolso negro de cuero")
        assert (result.primary_intent, result.sub_intent) == (IntentType.TRANSACTIONAL, "product_search")


class TestIsGreetingOnly:

    @pytest.mark.parametrize("text", GREETING_ONLY + ["bonjour", "salut ça va ?", "what's up"])
    def test_true(self, text):
        assert is_greeting_only(text) is True

    @pytest.mark.parametrize("text", GREETING_PLUS_CONTENT + [
        "hola y adios", "hola 123", "hello there, i need help", "hi all, where is my order",
        "", "   ", "busco un bolso",
    ])
    def test_false(self, text):
        assert is_greeting_only(text) is False

    def test_long_message_is_never_only_a_greeting(self):
        # Limite de 80 caracteres: un saludo puro es corto.
        assert is_greeting_only("hola " * 20) is False
