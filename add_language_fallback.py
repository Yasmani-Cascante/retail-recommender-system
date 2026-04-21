"""
Script para agregar lógica de language fallback a ShopifyKnowledgeBase.get_answer()

Este script:
1. Refactoriza get_answer() para usar un helper _get_answer_single_language()
2. Agrega lógica de fallback: fr → es → en
3. Mantiene backward compatibility completo
"""

import os
import re

file_path = r"C:\Users\yasma\Desktop\retail-recommender-system\src\api\core\knowledge_base_v2.py"

print("=" * 70)
print("AGREGANDO LANGUAGE FALLBACK LOGIC")
print("=" * 70)

# Leer archivo
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Backup
backup_path = file_path + ".backup_language_fallback"
with open(backup_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n✅ Backup creado: {backup_path}")

# ═══════════════════════════════════════════════════════════════════════════
# PASO 1: Buscar el método get_answer() y extraer su contenido
# ═══════════════════════════════════════════════════════════════════════════

# Encontrar el inicio del método get_answer
start_pattern = r'(    async def get_answer\([^)]+\)[^:]*:)'
start_match = re.search(start_pattern, content)

if not start_match:
    print("❌ ERROR: No se encontró el método get_answer()")
    exit(1)

start_pos = start_match.start()

# Encontrar el final (siguiente método que empieza con "    async def " o "    def ")
end_pattern = r'\n    (async )?def '
end_matches = list(re.finditer(end_pattern, content[start_pos + 100:]))

if not end_matches:
    print("❌ ERROR: No se encontró el final del método get_answer()")
    exit(1)

end_pos = start_pos + 100 + end_matches[0].start()

# Extraer el método completo
old_get_answer = content[start_pos:end_pos]

print(f"\n✅ Método get_answer() encontrado ({len(old_get_answer)} chars)")

# ═══════════════════════════════════════════════════════════════════════════
# PASO 2: Crear el nuevo método get_answer() con fallback logic
# ═══════════════════════════════════════════════════════════════════════════

new_get_answer = '''    async def get_answer(
        self,
        sub_intent: InformationalSubIntent,
        language: str = "es",
        category: Optional[str] = None
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Get Knowledge Base answer with triple-layer cache and language fallback.
        
        Fallback chain:
        1. Redis cache (fast, <1ms)
        2. PostgreSQL buffer (medium, <10ms)
        3. Shopify API (slow, 100-300ms)
        4. Language fallback (try es → en if requested language not found)
        5. Hardcoded KB (last resort, if enabled)
        
        Args:
            sub_intent: Informational intent
            language: Language code (es, en, pt, fr, etc.)
            category: Product category (ZAPATOS, VESTIDOS, etc)
            
        Returns:
            KnowledgeBaseAnswer or None
            
        Example:
            >>> answer = await kb.get_answer(
            >>>     sub_intent=InformationalSubIntent.POLICY_RETURN,
            >>>     language="fr",  # Falls back to 'es' if 'fr' not found
            >>>     category="ZAPATOS"
            >>> )
            >>> print(answer.answer)
        """
        sub_intent_str = sub_intent.value if hasattr(sub_intent, 'value') else str(sub_intent)
        
        # Try with requested language first
        result = await self._get_answer_single_language(
            sub_intent_str, 
            language, 
            category
        )
        
        if result:
            return result
        
        # ═══════════════════════════════════════════════════════════════════
        # LANGUAGE FALLBACK: Try alternative languages
        # ═══════════════════════════════════════════════════════════════════
        
        # Define fallback language chain
        fallback_languages = []
        if language not in ['es', 'en']:
            # If requested language is not es/en, try es first, then en
            fallback_languages = ['es', 'en']
            logger.info(
                f"Language '{language}' not found. "
                f"Attempting fallback chain: {fallback_languages}"
            )
        elif language == 'en':
            # If requested en, try es as fallback
            fallback_languages = ['es']
            logger.info(f"English content not found. Attempting Spanish fallback.")
        # Note: If language == 'es', no fallback (es is the default)
        
        # Try each fallback language
        for fallback_lang in fallback_languages:
            logger.info(
                f"Trying fallback language: {fallback_lang} "
                f"(original: {language})"
            )
            
            result = await self._get_answer_single_language(
                sub_intent_str,
                fallback_lang,
                category
            )
            
            if result:
                logger.info(
                    f"✅ Language fallback successful: "
                    f"{language} → {fallback_lang}"
                )
                return result
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 4: FALLBACK TO HARDCODED KB (Last resort)
        # ═══════════════════════════════════════════════════════════════════
        
        if self.enable_fallback and self.fallback_kb:
            logger.warning(
                f"⚠️ All layers and language fallbacks failed. "
                f"Falling back to hardcoded KB: "
                f"{sub_intent_str}/{language}/{category or 'general'}"
            )
            
            try:
                # Try to get from hardcoded KB
                # Note: Only pass sub_intent (other params may not be supported)
                fallback_answer = self.fallback_kb.get_answer(
                    sub_intent=sub_intent
                )
                
                if fallback_answer:
                    logger.info("✅ Fallback KB (hardcoded) returned answer")
                    return fallback_answer
                    
            except Exception as e:
                logger.error(f"Fallback KB error: {e}", exc_info=True)
        
        # ═══════════════════════════════════════════════════════════════════
        # NO ANSWER FOUND
        # ═══════════════════════════════════════════════════════════════════
        
        logger.warning(
            f"❌ No answer found for: {sub_intent_str}/{language}/{category or 'general'} "
            f"(tried all fallbacks)"
        )
        return None
    
    # ──────────────────────────────────────────────────────────────────────
    # INTERNAL HELPER - Single Language Query
    # ──────────────────────────────────────────────────────────────────────
    
    async def _get_answer_single_language(
        self,
        sub_intent_str: str,
        language: str,
        category: Optional[str]
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Get answer for a specific language without fallback.
        
        This is an internal helper method used by get_answer() to try
        each language in the fallback chain.
        
        Args:
            sub_intent_str: Sub-intent as string
            language: Language code to try
            category: Product category
            
        Returns:
            KnowledgeBaseAnswer or None
        """
        
        logger.info(
            f"KB query: sub_intent={sub_intent_str}, "
            f"language={language}, category={category}"
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 1: REDIS CACHE (Hot, <1ms)
        # ═══════════════════════════════════════════════════════════════════
        
        try:
            cached = await self._get_from_cache(sub_intent_str, language, category)
            if cached:
                logger.info(f"✅ Cache HIT (Redis): {sub_intent_str}/{language}/{category or 'general'}")
                return self._kb_answer_to_knowledge_base_answer(
                    cached, 
                    sub_intent=sub_intent_str,
                    cache_hit=True
                )
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 2: POSTGRESQL BUFFER (Warm, <10ms)
        # ═══════════════════════════════════════════════════════════════════
        
        try:
            buffered = await self._get_from_buffer(sub_intent_str, language, category)
            
            if buffered:
                # Check if fresh (not stale)
                is_fresh = buffered.is_fresh(max_age_hours=self.buffer_max_age.total_seconds() / 3600)
                
                if is_fresh:
                    logger.info(
                        f"✅ Buffer HIT (PostgreSQL): {sub_intent_str}/{language}/{category or 'general'}"
                    )
                    
                    # Store in Redis for next time
                    kb_answer = kb_content_to_answer(buffered, cache_hit=False)
                    await self._store_in_cache(sub_intent_str, language, category, kb_answer)
                    
                    return self._kb_answer_to_knowledge_base_answer(
                        kb_answer,
                        sub_intent=sub_intent_str,
                        cache_hit=False
                    )
                else:
                    logger.warning(
                        f"⚠️ Buffer STALE (PostgreSQL): {sub_intent_str}/{language}/{category or 'general'} "
                        f"(age: {datetime.utcnow() - buffered.last_synced})"
                    )
                    # Continue to Layer 3 to refresh
        except Exception as e:
            logger.error(f"PostgreSQL buffer error: {e}", exc_info=True)
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 3: SHOPIFY API (Cold, 100-300ms) - Only if configured
        # ═══════════════════════════════════════════════════════════════════
        
        if self.shopify:
            try:
                logger.info(f"Fetching from Shopify API: {sub_intent_str}/{language}/{category or 'general'}")
                
                # TODO: Implement direct Shopify fetch
                # For now, trigger background sync and use stale buffer
                logger.warning("Direct Shopify fetch not implemented yet. Using stale buffer if available.")
                
                # Use stale buffer as last resort
                if buffered:
                    logger.info("Using STALE buffer (better than nothing)")
                    kb_answer = kb_content_to_answer(buffered, cache_hit=False)
                    return self._kb_answer_to_knowledge_base_answer(
                        kb_answer,
                        sub_intent=sub_intent_str,
                        cache_hit=False
                    )
                    
            except Exception as e:
                logger.error(f"Shopify API error: {e}", exc_info=True)
        
        # No answer found for this specific language
        return None

'''

# ═══════════════════════════════════════════════════════════════════════════
# PASO 3: Reemplazar en el contenido
# ═══════════════════════════════════════════════════════════════════════════

new_content = content[:start_pos] + new_get_answer + content[end_pos:]

# Escribir archivo modificado
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("\n✅ FIX APLICADO")
print("\n📋 Cambios:")
print("   1. get_answer() ahora intenta language fallback:")
print("      - fr → es → en")
print("      - pt → es → en")
print("      - cualquier otro → es → en")
print("   2. Nuevo método _get_answer_single_language() (helper interno)")
print("   3. Fallback KB ahora solo recibe sub_intent (fix signature error)")
print("\n🧪 Siguiente paso:")
print("   python tests/integration/kb/diagnose_kb_test.py")

print("\n" + "=" * 70)
print("COMPLETADO")
print("=" * 70)