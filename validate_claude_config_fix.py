#!/usr/bin/env python3
"""
Script de Validación de Configuración Claude
===========================================

Valida que la configuración centralizada Claude esté funcionando correctamente
después de las correcciones aplicadas.
"""

import sys
import os
from dotenv import load_dotenv

# 🚀 CORRECCIÓN: Cargar variables de entorno desde .env
load_dotenv()

sys.path.append('src')

def validate_claude_configuration():
    """Valida la configuración Claude completa"""
    
    print("🔧 VALIDACIÓN DE CONFIGURACIÓN CLAUDE CENTRALIZADA")
    print("=" * 60)
    
    try:
        # Verificar que .env se cargó correctamente
        api_key_env = os.getenv('ANTHROPIC_API_KEY')
        print(f"🔑 API Key desde entorno: {'Configurada' if api_key_env else 'NO CONFIGURADA'}")
        
        # Importar servicio de configuración
        from api.core.claude_config import get_claude_config_service, ClaudeModelTier
        
        print("✅ Importación exitosa del servicio Claude")
        
        # Crear instancia del servicio
        claude_service = get_claude_config_service()
        
        print(f"✅ Servicio Claude inicializado")
        print(f"   Model Tier: {claude_service.claude_model_tier.name}")
        print(f"   Model Name: {claude_service.claude_model_tier.value}")
        print(f"   Region: {claude_service.claude_region}")
        
        # Validar configuración
        validation_result = claude_service.validate_configuration()
        
        print(f"\n📊 RESULTADO DE VALIDACIÓN:")
        print(f"   Estado: {'✅ VÁLIDA' if validation_result['valid'] else '❌ INVÁLIDA'}")
        
        if validation_result.get('issues'):
            print(f"   Issues: {len(validation_result['issues'])}")
            for issue in validation_result['issues']:
                print(f"     - {issue}")
        
        if validation_result.get('warnings'):
            print(f"   Warnings: {len(validation_result['warnings'])}")
            for warning in validation_result['warnings']:
                print(f"     - {warning}")
        
        # Mostrar métricas
        metrics = claude_service.get_metrics()
        print(f"\n📈 MÉTRICAS DE CONFIGURACIÓN:")
        for key, value in metrics.items():
            print(f"   {key}: {value}")
        
        # Probar resolución de diferentes tiers
        print(f"\n🧪 PRUEBA DE RESOLUCIÓN DE TIERS:")
        test_tiers = ["HAIKU", "SONNET", "OPUS", "invalid"]
        
        for tier_name in test_tiers:
            try:
                tier = ClaudeModelTier.from_string(tier_name)
                print(f"   ✅ {tier_name} -> {tier.value}")
            except ValueError as e:
                print(f"   ❌ {tier_name} -> {e}")
        
        # Probar configuración de modelo
        print(f"\n⚙️ CONFIGURACIÓN DE MODELO:")
        config = claude_service.get_model_config()
        print(f"   Model: {config.model_name}")
        print(f"   Max Tokens: {config.max_tokens}")
        print(f"   Temperature: {config.temperature}")
        print(f"   Cost per 1K tokens: ${config.cost_per_1k_tokens}")
        
        # Resultado final
        if validation_result['valid']:
            print(f"\n🎉 CONFIGURACIÓN CLAUDE COMPLETAMENTE VÁLIDA")
            print(f"✅ El warning 'Invalid CLAUDE_MODEL_TIER: SONNET' ha sido resuelto")
            return True
        else:
            print(f"\n⚠️ CONFIGURACIÓN REQUIERE ATENCIÓN")
            return False
        
    except Exception as e:
        print(f"❌ ERROR DURANTE VALIDACIÓN: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔍 VALIDADOR DE CONFIGURACIÓN CLAUDE")
    print("Verificando corrección del warning 'Invalid CLAUDE_MODEL_TIER: SONNET'\n")
    
    success = validate_claude_configuration()
    
    if success:
        print("\n" + "="*60)
        print("✅ VALIDACIÓN EXITOSA - CONFIGURACIÓN CLAUDE OPERATIVA")
        print("🚀 El sistema está listo para usar la configuración centralizada")
    else:
        print("\n" + "="*60)
        print("❌ VALIDACIÓN FALLÓ - REVISAR CONFIGURACIÓN")
        sys.exit(1)
