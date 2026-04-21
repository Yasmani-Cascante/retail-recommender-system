"enfoque exhaustivo para asegurar que el Knowledge Base entienda preguntas,"
"adapte respuestas y rastree métricas correctamente."

import pytest
from src.api.core.knowledge_base import SimpleKnowledgeBase, get_knowledge_base, get_answer
from src.api.core.intent_types import InformationalSubIntent, KnowledgeBaseAnswer

def test_knowledge_base_initialization():
    kb = SimpleKnowledgeBase()
    assert kb.metrics["total_queries"] == 0
    assert kb.content is not None

def test_get_answer_policy_return_general():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.POLICY_RETURN)
    assert answer is not None
    assert "Política de Devoluciones" in answer.answer
    assert "policies/returns.md" in answer.sources

def test_get_answer_policy_return_contextual():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.POLICY_RETURN, product_context=["ZAPATOS"])
    assert answer is not None
    assert "Devolución de Calzado" in answer.answer
    
    answer_vestidos = kb.get_answer(InformationalSubIntent.POLICY_RETURN, product_context=["VESTIDOS"])
    assert "Devolución de Vestidos" in answer_vestidos.answer

def test_get_answer_shipping_cost():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.POLICY_SHIPPING, query="cuánto cuesta el envío")
    assert answer is not None
    assert "Costos de Envío" in answer.answer
    assert "policies/shipping_cost.md" in answer.sources

def test_get_answer_shipping_time():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.POLICY_SHIPPING, query="cuánto tarda en llegar")
    assert answer is not None
    assert "Tiempos de Entrega" in answer.answer
    assert "policies/shipping_time.md" in answer.sources

def test_get_answer_shipping_general():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.POLICY_SHIPPING)
    assert answer is not None
    assert "Información de Envío" in answer.answer
    assert "policies/shipping.md" in answer.sources

def test_get_answer_payment():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.POLICY_PAYMENT)
    assert answer is not None
    assert "Métodos de Pago Aceptados" in answer.answer

def test_get_answer_material_contextual():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.PRODUCT_MATERIAL, product_context=["ZAPATOS"])
    assert "Materiales de Calzado" in answer.answer

def test_get_answer_size_contextual():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.PRODUCT_SIZE, product_context=["VESTIDOS"])
    assert "Guía de Tallas - Vestidos" in answer.answer

def test_get_answer_care_contextual():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.PRODUCT_CARE, product_context=["VESTIDOS"])
    assert "Cuidado de Vestidos" in answer.answer

def test_get_answer_unknown_keyword_detection():
    kb = SimpleKnowledgeBase()
    # Test return keyword
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="quiero devolver algo")
    assert answer.sub_intent == InformationalSubIntent.POLICY_RETURN
    
    # Test shipping keyword
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="mi paquete no llega")
    assert answer.sub_intent == InformationalSubIntent.POLICY_SHIPPING
    
    # Test payment keyword
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="puedo pagar con paypal")
    assert answer.sub_intent == InformationalSubIntent.POLICY_PAYMENT
    
    # Test material keyword
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="de que tela es")
    assert answer.sub_intent == InformationalSubIntent.PRODUCT_MATERIAL
    
    # Test size keyword
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="que talla soy")
    assert answer.sub_intent == InformationalSubIntent.PRODUCT_SIZE
    
    # Test care keyword
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="como lavar esto")
    assert answer.sub_intent == InformationalSubIntent.PRODUCT_CARE

def test_get_answer_fallback_to_general_faq():
    kb = SimpleKnowledgeBase()
    answer = kb.get_answer(InformationalSubIntent.UNKNOWN, query="hola que tal")
    assert "No pudimos clasificar tu pregunta" in answer.answer

def test_get_metrics():
    kb = SimpleKnowledgeBase()
    kb.get_answer(InformationalSubIntent.POLICY_RETURN)
    metrics = kb.get_metrics()
    assert metrics["total_queries"] == 1
    assert metrics["successful_answers"] == 1
    assert metrics["success_rate"] == 1.0

def test_singleton_and_public_api():
    kb1 = get_knowledge_base()
    kb2 = get_knowledge_base()
    assert kb1 is kb2
    
    answer = get_answer(InformationalSubIntent.POLICY_RETURN)
    assert answer is not None