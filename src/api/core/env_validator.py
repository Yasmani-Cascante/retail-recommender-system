"""
Validador mejorado para configuración con manejo robusto de errores.

Este módulo proporciona validación adicional y limpieza automática
de variables de entorno para prevenir errores comunes.
"""

import os
import re
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class EnvValidator:
    """Validador y limpiador de variables de entorno."""
    
    @staticmethod
    def clean_env_value(value: str) -> str:
        """
        Limpia un valor de variable de entorno eliminando comentarios y espacios.
        
        Args:
            value: Valor de la variable de entorno
            
        Returns:
            Valor limpio
        """
        if not isinstance(value, str):
            return value
            
        # Eliminar comentarios inline (todo después de #)
        if '#' in value:
            value = value.split('#')[0]
            logger.warning(f"Comentario inline detectado y removido: {value}")
        
        # Eliminar espacios al inicio y final
        return value.strip()
    
    @staticmethod
    def validate_boolean(value: str, variable_name: str) -> bool:
        """
        Valida y convierte un valor a boolean de manera robusta.
        
        Args:
            value: Valor a convertir
            variable_name: Nombre de la variable para logging
            
        Returns:
            Valor boolean
        """
        if not isinstance(value, str):
            return bool(value)
            
        # Limpiar el valor primero
        clean_value = EnvValidator.clean_env_value(value).lower()
        
        # Valores que se consideran True
        true_values = {'true', '1', 'yes', 'on', 'enabled'}
        # Valores que se consideran False
        false_values = {'false', '0', 'no', 'off', 'disabled', ''}
        
        if clean_value in true_values:
            return True
        elif clean_value in false_values:
            return False
        else:
            logger.error(f"Valor boolean inválido para {variable_name}: '{value}' (limpio: '{clean_value}')")
            raise ValueError(f"Cannot convert '{value}' to boolean for {variable_name}")
    
    @staticmethod
    def validate_integer(value: str, variable_name: str, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
        """
        Valida y convierte un valor a entero de manera robusta.
        
        Args:
            value: Valor a convertir
            variable_name: Nombre de la variable para logging
            min_val: Valor mínimo permitido
            max_val: Valor máximo permitido
            
        Returns:
            Valor entero
        """
        if isinstance(value, int):
            result = value
        else:
            clean_value = EnvValidator.clean_env_value(str(value))
            try:
                result = int(clean_value)
            except ValueError:
                logger.error(f"Valor entero inválido para {variable_name}: '{value}' (limpio: '{clean_value}')")
                raise ValueError(f"Cannot convert '{value}' to integer for {variable_name}")
        
        # Validar rangos si se especifican
        if min_val is not None and result < min_val:
            raise ValueError(f"{variable_name} must be >= {min_val}, got {result}")
        if max_val is not None and result > max_val:
            raise ValueError(f"{variable_name} must be <= {max_val}, got {result}")
            
        return result
    
    @staticmethod
    def validate_float(value: str, variable_name: str, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
        """
        Valida y convierte un valor a float de manera robusta.
        
        Args:
            value: Valor a convertir
            variable_name: Nombre de la variable para logging
            min_val: Valor mínimo permitido
            max_val: Valor máximo permitido
            
        Returns:
            Valor float
        """
        if isinstance(value, (int, float)):
            result = float(value)
        else:
            clean_value = EnvValidator.clean_env_value(str(value))
            try:
                result = float(clean_value)
            except ValueError:
                logger.error(f"Valor float inválido para {variable_name}: '{value}' (limpio: '{clean_value}')")
                raise ValueError(f"Cannot convert '{value}' to float for {variable_name}")
        
        # Validar rangos si se especifican
        if min_val is not None and result < min_val:
            raise ValueError(f"{variable_name} must be >= {min_val}, got {result}")
        if max_val is not None and result > max_val:
            raise ValueError(f"{variable_name} must be <= {max_val}, got {result}")
            
        return result
    
    @staticmethod
    def clean_env_file(env_file_path: str) -> Dict[str, str]:
        """
        Lee y limpia un archivo .env, removiendo comentarios inline y validando sintaxis.
        
        Args:
            env_file_path: Ruta al archivo .env
            
        Returns:
            Diccionario con variables limpias
        """
        if not os.path.exists(env_file_path):
            logger.warning(f"Archivo .env no encontrado: {env_file_path}")
            return {}
        
        cleaned_vars = {}
        issues_found = []
        
        with open(env_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Ignorar líneas vacías y comentarios
                if not line or line.startswith('#'):
                    continue
                    
                # Verificar si tiene formato var=value
                if '=' not in line:
                    issues_found.append(f"Línea {line_num}: Formato inválido: {line}")
                    continue
                
                var_name, var_value = line.split('=', 1)
                var_name = var_name.strip()
                
                # Detectar y limpiar comentarios inline
                original_value = var_value
                cleaned_value = EnvValidator.clean_env_value(var_value)
                
                if original_value != cleaned_value:
                    issues_found.append(f"Línea {line_num}: Comentario inline removido en {var_name}")
                
                cleaned_vars[var_name] = cleaned_value
        
        # Reportar problemas encontrados
        if issues_found:
            logger.warning("Problemas encontrados en archivo .env:")
            for issue in issues_found:
                logger.warning(f"  - {issue}")
        
        return cleaned_vars
    
    @staticmethod
    def validate_env_file_and_create_backup(env_file_path: str = ".env") -> bool:
        """
        Valida un archivo .env y crea una versión limpia como respaldo.
        
        Args:
            env_file_path: Ruta al archivo .env
            
        Returns:
            True si se necesitaron correcciones, False si estaba correcto
        """
        try:
            original_vars = {}
            
            # Leer archivo original
            if os.path.exists(env_file_path):
                with open(env_file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                    
                # Usar python-dotenv para obtener las variables como las lee realmente
                from dotenv import dotenv_values
                original_vars = dotenv_values(env_file_path)
            
            # Limpiar variables
            cleaned_vars = EnvValidator.clean_env_file(env_file_path)
            
            # Comparar si hay diferencias
            corrections_needed = False
            for var_name, clean_value in cleaned_vars.items():
                original_value = original_vars.get(var_name, "")
                if original_value != clean_value:
                    corrections_needed = True
                    logger.info(f"Corrección requerida en {var_name}: '{original_value}' → '{clean_value}'")
            
            # Si hay correcciones, crear archivo respaldo
            if corrections_needed:
                backup_path = f"{env_file_path}.backup"
                clean_path = f"{env_file_path}.cleaned"
                
                # Crear respaldo del original
                if os.path.exists(env_file_path):
                    import shutil
                    shutil.copy2(env_file_path, backup_path)
                    logger.info(f"Respaldo creado: {backup_path}")
                
                # Crear versión limpia
                with open(clean_path, 'w', encoding='utf-8') as f:
                    f.write("# Archivo .env limpio - generado automáticamente\n")
                    f.write("# Use este archivo para reemplazar el original si hay problemas\n\n")
                    
                    for var_name, clean_value in cleaned_vars.items():
                        f.write(f"{var_name}={clean_value}\n")
                        
                logger.info(f"Archivo limpio creado: {clean_path}")
                logger.info("Para aplicar correcciones, ejecute: cp .env.cleaned .env")
            
            return corrections_needed
            
        except Exception as e:
            logger.error(f"Error validando archivo .env: {str(e)}")
            return False

# Ejemplo de uso
if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Validar archivo .env actual
    corrections_needed = EnvValidator.validate_env_file_and_create_backup()
    
    if corrections_needed:
        print("⚠️ Correcciones requeridas en archivo .env")
        print("📋 Ver logs para detalles")
        print("🔧 Para aplicar: cp .env.cleaned .env")
    else:
        print("✅ Archivo .env está correcto")
