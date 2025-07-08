class ClaudeQuickWinIntegration:
    """Quick win: Optimizar ConversationAIManager existente"""
    
    def __init__(self, existing_ai_manager):
        self.ai_manager = existing_ai_manager
        self.setup_optimizations()
    
    def setup_optimizations(self):
        # 1. Connection pooling
        self.ai_manager.claude.http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )

    # 2. Response caching
    self.response_cache = TTLCache(maxsize=1000, ttl=1800)  # 30 min cache

    # 3. Rate limiting
    self.rate_limiter = AsyncLimiter(100, 60)  # 100 calls per minute

async def optimized_conversation(self, user_message: str, context: Dict):
    """Conversación optimizada con Claude"""
    cache_key = f"conv:{hash(user_message)}:{context.get('market_id', 'default')}"

    # Check cache first
    if cache_key in self.response_cache:
        return self.response_cache[cache_key]

    # Rate limiting
    async with self.rate_limiter:
        response = await self.ai_manager.process_conversation(
            user_message, context, include_recommendations=True
        )

    # Cache successful responses
    if response.get("intent_analysis", {}).get("confidence", 0) > 0.7:
        self.response_cache[cache_key] = response

    return response