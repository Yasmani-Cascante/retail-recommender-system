# Test en terminal Python o crear script test_intent_simple.py
from src.api.core.intent_detection import detect_intent

# Test informational
result = detect_intent("¿cuál es la política de devolución?")
print(f"Intent: {result.primary_intent}")
print(f"Confidence: {result.confidence}")
print(f"Reasoning: {result.reasoning}")

# Test transactional  
result = detect_intent("busco vestidos elegantes")
print(f"Intent: {result.primary_intent}")
