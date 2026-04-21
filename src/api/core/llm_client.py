from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
import os, logging

log = logging.getLogger(__name__)

class LLMResponse:
    """Respuesta normalizada, independiente del proveedor."""
    def __init__(self, content: str, model: str, input_tokens: int, output_tokens: int):
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

class UnifiedLLMClient:
    """
    Wrapper que abstrae Anthropic vs OpenRouter.
    Expone un único método async: complete(system, user) -> LLMResponse
    El caller nunca sabe qué proveedor se está usando.
    """

    def __init__(self, provider: str, model: str, max_tokens: int, temperature: float):
        self.provider = provider  # 'anthropic' | 'openrouter'
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        if provider == 'openrouter':
            api_key = os.environ.get('OPENROUTER_API_KEY')
            if not api_key:
                raise ValueError('OPENROUTER_API_KEY env var not set')
            self._client = AsyncOpenAI(
                base_url='https://openrouter.ai/api/v1',
                api_key=api_key,
                default_headers={
                    'HTTP-Referer': 'https://retail-recommender-lzf2y6pspa-uc.a.run.app',
                    'X-Title': 'RetailRecommender',
                }
            )
        else:  # 'anthropic' (default)
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            self._client = AsyncAnthropic(api_key=api_key)

    async def complete(self, system: str, user: str) -> LLMResponse:
        """
        Llama al LLM y devuelve LLMResponse normalizada.
        Maneja las diferencias de API entre Anthropic y OpenAI internamente.
        """
        if self.provider == 'openrouter':
            return await self._complete_openrouter(system, user)
        else:
            return await self._complete_anthropic(system, user)

    async def _complete_openrouter(self, system: str, user: str) -> LLMResponse:
        resp = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user',   'content': user},
            ]
        )
        msg = resp.choices[0].message

        # ── Extraer content de forma defensiva ──────────────────────────────────
        # Los modelos ':thinking' de OpenRouter (ej. lfm-2.5-1.2b-thinking)
        # ponen su output en msg.reasoning y dejan msg.content = None.
        # Los modelos ':instruct' / standard ponen su output directamente
        # en msg.content como es esperado por el SDK de OpenAI.
        #
        # Estrategia de extraccion (en orden de preferencia):
        #   1. msg.content         — respuesta directa (todos los modelos standard)
        #   2. msg.reasoning       — output de modelos thinking via atributo
        #   3. model_extra[reasoning_content] — algunas versiones de OpenAI SDK
        #                             exponen campos extra en model_extra
        # Si todo es None/vacio, lanzar ValueError para que el caller ejecute
        # el fallback (Haiku) en lugar de propagar None silenciosamente.
        content = msg.content

        if not content:
            # Intento 1: atributo reasoning directo (modelos thinking en OpenRouter)
            content = getattr(msg, 'reasoning', None)

        if not content:
            # Intento 2: OpenAI SDK a veces expone campos extra en model_extra
            content = (getattr(msg, 'model_extra', None) or {}).get('reasoning_content')

        if not content:
            raise ValueError(
                f'OpenRouter returned empty content and reasoning for model={self.model}. '
                f'Check model ID and tier (instruct vs thinking).'
            )

        return LLMResponse(
            content=content,
            model=resp.model,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )

    async def _complete_anthropic(self, system: str, user: str) -> LLMResponse:
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{'role': 'user', 'content': user}]
        )
        return LLMResponse(
            content=resp.content[0].text,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )