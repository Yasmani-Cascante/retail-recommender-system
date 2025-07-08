# Integración Claude - Guía de Configuración

## Configuración Inicial

### 1. Variables de Entorno Requeridas

```bash
# Configuración básica Claude
ANTHROPIC_API_KEY=your_real_api_key_here
AI_CONVERSATION_ENABLED=true
CLAUDE_MODEL=claude-3-sonnet-20240229

# Configuración avanzada (opcional)
CLAUDE_MAX_TOKENS=2000
CLAUDE_TEMPERATURE=0.7
USE_PERPLEXITY_VALIDATION=false
```

### 2. Obtener API Key de Anthropic

1. Ir a [console.anthropic.com](https://console.anthropic.com)
2. Crear cuenta o iniciar sesión
3. Generar API key en la sección "Keys"
4. Agregar a .env: `ANTHROPIC_API_KEY=sk-ant-...`

### 3. Activar Sistema de Conversación

```bash
# En .env
AI_CONVERSATION_ENABLED=true
```

## Testing

### Prueba Rápida
```bash
python test_claude_quick.py
```

### Prueba Completa
```bash
python test_claude_integration.py
```

### Testing HTTP
```bash
# Iniciar servidor
python run.py

# En otra terminal
bash test_claude_api.sh
```

## Endpoints Disponibles

### Conversación Básica
```bash
POST /v1/conversation/chat
GET /v1/conversation/quick-chat
```

### Conversación con Recomendaciones
```bash
POST /v1/conversation-enhanced/chat-with-recommendations
```

### Métricas y Salud
```bash
GET /v1/conversation/metrics
GET /v1/conversation/health
```

## Troubleshooting

### Claude no disponible
- Verificar ANTHROPIC_API_KEY en .env
- Verificar AI_CONVERSATION_ENABLED=true
- Verificar conexión a internet

### Errores de import
- Verificar que todos los archivos están en las ubicaciones correctas
- Ejecutar setup_claude_integration.sh de nuevo

### Latencia alta
- Cambiar a claude-3-haiku-20240307 para mayor velocidad
- Reducir CLAUDE_MAX_TOKENS
- Verificar conexión de red
