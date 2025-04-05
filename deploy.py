#!/usr/bin/env python3
"""
Script de despliegue unificado para el sistema de recomendaciones retail.

Este script gestiona todas las fases de despliegue progresivo del sistema,
desde la construcción de imágenes Docker hasta su despliegue en Google Cloud Run.
"""

import os
import sys
import argparse
import subprocess
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Union, Tuple

# Configurar logging
log_filename = f"deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename)
    ]
)
logger = logging.getLogger(__name__)

# Configuración del proyecto
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "retail-recommendations-449216")
REGION = os.environ.get("GCP_REGION", "us-central1")
SERVICE_ACCOUNT = os.environ.get("GCP_SERVICE_ACCOUNT", "")

# Configuración de las fases
PHASES = {
    1: {
        "name": "Pre-computación de embeddings",
        "image": "retail-recommender-precomputed",
        "dockerfile": "Dockerfile.poetry",
        "service": "retail-recommender-precomputed",
        "memory": "2Gi",
        "cpu": 2,
        "min_instances": 1,
        "max_instances": 10,
        "timeout": "5m"
    },
    2: {
        "name": "Sistema de caché distribuida",
        "image": "retail-recommender-cached",
        "dockerfile": "Dockerfile.cached",
        "service": "retail-recommender-cached",
        "memory": "2Gi",
        "cpu": 2,
        "min_instances": 1,
        "max_instances": 10,
        "timeout": "5m",
        "redis": True
    },
    3: {
        "name": "Arquitectura dividida (gRPC)",
        "services": [
            {
                "name": "Servidor gRPC",
                "image": "retail-recommender-grpc",
                "dockerfile": "Dockerfile.grpc",
                "service": "retail-recommender-grpc",
                "memory": "4Gi",
                "cpu": 4,
                "min_instances": 1,
                "max_instances": 10,
                "timeout": "10m"
            },
            {
                "name": "API distribuida",
                "image": "retail-recommender-api",
                "dockerfile": "Dockerfile.api",
                "service": "retail-recommender-api",
                "memory": "1Gi",
                "cpu": 1,
                "min_instances": 1,
                "max_instances": 20,
                "timeout": "5m",
                "depends_on": "retail-recommender-grpc"
            }
        ]
    }
}

def run_command(cmd: List[str], check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    """
    Ejecuta un comando del sistema y registra su salida.
    
    Args:
        cmd: Lista con el comando y sus argumentos
        check: Si es True, genera una excepción si el comando falla
        capture_output: Si es True, captura la salida del comando
        
    Returns:
        Resultado del comando
    """
    cmd_str = ' '.join(cmd)
    logger.info(f"Ejecutando: {cmd_str}")
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=capture_output, 
            text=True, 
            check=False
        )
        
        if result.stdout and len(result.stdout.strip()) > 0:
            for line in result.stdout.split('\n'):
                if line.strip():
                    logger.info(f"STDOUT: {line.strip()}")
        
        if result.stderr and len(result.stderr.strip()) > 0:
            for line in result.stderr.split('\n'):
                if line.strip():
                    if result.returncode != 0:
                        logger.error(f"STDERR: {line.strip()}")
                    else:
                        logger.warning(f"STDERR: {line.strip()}")
        
        if check and result.returncode != 0:
            logger.error(f"❌ Comando falló con código de salida {result.returncode}: {cmd_str}")
            raise Exception(f"Error ejecutando comando: {cmd_str}")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Error ejecutando comando: {cmd_str}")
        logger.error(f"  Excepción: {str(e)}")
        if check:
            raise
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

def check_prerequisites() -> bool:
    """
    Verifica que estén disponibles todas las herramientas necesarias.
    
    Returns:
        True si todas las herramientas están disponibles, False en caso contrario
    """
    prereqs = [
        ("docker", ["docker", "--version"]),
        ("gcloud", ["gcloud", "--version"]),
        ("poetry", ["poetry", "--version"])
    ]
    
    missing = []
    
    for name, cmd in prereqs:
        try:
            run_command(cmd)
            logger.info(f"✓ {name} encontrado")
        except:
            logger.error(f"✗ {name} no encontrado")
            missing.append(name)
    
    if missing:
        logger.error(f"Requisitos faltantes: {', '.join(missing)}")
        logger.error("Por favor, instale las herramientas faltantes antes de continuar")
        return False
    
    return True

def configure_gcloud() -> bool:
    """
    Configura gcloud con el proyecto y región actuales.
    
    Returns:
        True si la configuración fue exitosa, False en caso contrario
    """
    try:
        # Configurar proyecto
        run_command(["gcloud", "config", "set", "project", PROJECT_ID])
        
        # Configurar región
        run_command(["gcloud", "config", "set", "run/region", REGION])
        
        # Verificar la configuración
        run_command(["gcloud", "config", "list"])
        
        logger.info(f"✓ gcloud configurado exitosamente para el proyecto {PROJECT_ID} en {REGION}")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error configurando gcloud: {e}")
        return False

def build_and_push_image(image_name: str, dockerfile: str) -> bool:
    """
    Construye y sube una imagen Docker a Google Container Registry.
    
    Args:
        image_name: Nombre de la imagen
        dockerfile: Ruta al Dockerfile
        
    Returns:
        True si el proceso fue exitoso, False en caso contrario
    """
    try:
        tag = f"gcr.io/{PROJECT_ID}/{image_name}:latest"
        
        # Verificar que el Dockerfile existe
        if not Path(dockerfile).exists():
            logger.error(f"❌ Dockerfile no encontrado: {dockerfile}")
            return False
        
        # Construir imagen
        logger.info(f"🔨 Construyendo imagen {tag} con {dockerfile}...")
        run_command(["docker", "build", "-t", tag, "-f", dockerfile, "."])
        
        # Subir imagen a GCR
        logger.info(f"📤 Subiendo imagen {tag} a Google Container Registry...")
        run_command(["docker", "push", tag])
        
        logger.info(f"✓ Imagen {tag} construida y subida exitosamente")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error construyendo/subiendo imagen {image_name}: {e}")
        return False

def deploy_to_cloud_run(
    service_name: str, 
    image_name: str, 
    memory: str = "1Gi",
    cpu: int = 1,
    min_instances: int = 0,
    max_instances: int = 10,
    timeout: str = "5m",
    env_vars: Dict[str, str] = None
) -> bool:
    """
    Despliega una imagen en Google Cloud Run.
    
    Args:
        service_name: Nombre del servicio Cloud Run
        image_name: Nombre de la imagen (sin gcr.io/project)
        memory: Memoria asignada (formato GCP: 512Mi, 1Gi, etc.)
        cpu: Número de CPUs
        min_instances: Número mínimo de instancias
        max_instances: Número máximo de instancias
        timeout: Tiempo máximo de respuesta
        env_vars: Variables de entorno
        
    Returns:
        True si el despliegue fue exitoso, False en caso contrario
    """
    try:
        # Construir comando base
        tag = f"gcr.io/{PROJECT_ID}/{image_name}:latest"
        deploy_cmd = [
            "gcloud", "run", "deploy", service_name,
            "--image", tag,
            "--platform", "managed",
            "--region", REGION,
            "--memory", memory,
            "--cpu", str(cpu),
            "--min-instances", str(min_instances),
            "--max-instances", str(max_instances),
            "--timeout", timeout,
            "--allow-unauthenticated"
        ]
        
        # Agregar variables de entorno
        if env_vars:
            env_list = [f"{k}={v}" for k, v in env_vars.items()]
            deploy_cmd.extend(["--set-env-vars", ",".join(env_list)])
        
        # Agregar cuenta de servicio si está configurada
        if SERVICE_ACCOUNT:
            deploy_cmd.extend(["--service-account", SERVICE_ACCOUNT])
        
        # Ejecutar despliegue
        logger.info(f"🚀 Desplegando {service_name} en Cloud Run...")
        run_command(deploy_cmd)
        
        # Obtener URL del servicio
        url_cmd = [
            "gcloud", "run", "services", "describe", service_name,
            "--platform", "managed", 
            "--region", REGION, 
            "--format", "value(status.url)"
        ]
        result = run_command(url_cmd)
        
        service_url = result.stdout.strip()
        logger.info(f"✓ Servicio {service_name} desplegado exitosamente")
        logger.info(f"  URL: {service_url}")
        
        return True, service_url
    
    except Exception as e:
        logger.error(f"❌ Error desplegando servicio {service_name}: {e}")
        return False, None

def create_redis_instance(instance_name: str = "retail-recommender-redis") -> Tuple[bool, Optional[str]]:
    """
    Crea una instancia de Redis en Google Cloud Memorystore.
    
    Args:
        instance_name: Nombre de la instancia
        
    Returns:
        Tupla (éxito, dirección IP) donde éxito es True si la creación fue exitosa,
        y dirección IP es la IP de la instancia de Redis (o None si falló)
    """
    try:
        # Verificar si la instancia ya existe
        check_cmd = [
            "gcloud", "redis", "instances", "describe", instance_name,
            "--region", REGION,
            "--format", "json"
        ]
        
        try:
            result = run_command(check_cmd, check=False)
            if result.returncode == 0:
                logger.info(f"ℹ️ Instancia Redis {instance_name} ya existe")
                
                # Extraer IP de la salida
                import json
                import re
                
                # Intentar parsear como JSON
                try:
                    data = json.loads(result.stdout)
                    redis_host = data.get("host")
                    if redis_host:
                        logger.info(f"✓ IP de Redis: {redis_host}")
                        return True, redis_host
                except:
                    # Intentar extraer con regex si falla el JSON
                    match = re.search(r"host: (\d+\.\d+\.\d+\.\d+)", result.stdout)
                    if match:
                        redis_host = match.group(1)
                        logger.info(f"✓ IP de Redis: {redis_host}")
                        return True, redis_host
                
                logger.error("No se pudo extraer la IP de Redis de la salida")
                return False, None
        except:
            pass
        
        # Crear instancia
        logger.info(f"🔧 Creando instancia Redis {instance_name}...")
        create_cmd = [
            "gcloud", "redis", "instances", "create", instance_name,
            "--size", "1",
            "--region", REGION,
            "--redis-version", "redis_6_x"
        ]
        run_command(create_cmd)
        
        # Esperar a que la instancia esté lista
        logger.info("⏳ Esperando a que la instancia de Redis esté lista...")
        wait_cmd = [
            "gcloud", "redis", "instances", "wait", instance_name,
            "--region", REGION
        ]
        run_command(wait_cmd)
        
        # Obtener IP de Redis
        info_cmd = [
            "gcloud", "redis", "instances", "describe", instance_name,
            "--region", REGION
        ]
        info_result = run_command(info_cmd)
        
        # Extraer host de la salida
        import re
        match = re.search(r"host: (\d+\.\d+\.\d+\.\d+)", info_result.stdout)
        if match:
            redis_host = match.group(1)
            logger.info(f"✓ Instancia Redis creada: {redis_host}")
            return True, redis_host
        else:
            logger.error("No se pudo obtener la IP de Redis")
            return False, None
    
    except Exception as e:
        logger.error(f"❌ Error creando instancia Redis: {e}")
        return False, None

def deploy_phase1() -> bool:
    """
    Despliega la fase 1: Pre-computación de embeddings.
    
    Returns:
        True si el despliegue fue exitoso, False en caso contrario
    """
    phase = PHASES[1]
    logger.info(f"🚀 Iniciando despliegue de Fase 1: {phase['name']}")
    
    # Construir y subir imagen
    success = build_and_push_image(
        image_name=phase["image"],
        dockerfile=phase["dockerfile"]
    )
    
    if not success:
        return False
    
    # Desplegar en Cloud Run
    success, _ = deploy_to_cloud_run(
        service_name=phase["service"],
        image_name=phase["image"],
        memory=phase["memory"],
        cpu=phase["cpu"],
        min_instances=phase["min_instances"],
        max_instances=phase["max_instances"],
        timeout=phase["timeout"]
    )
    
    return success

def deploy_phase2(redis_host: Optional[str] = None) -> bool:
    """
    Despliega la fase 2: Sistema de caché distribuida.
    
    Args:
        redis_host: Dirección IP de Redis (si ya existe)
        
    Returns:
        True si el despliegue fue exitoso, False en caso contrario
    """
    phase = PHASES[2]
    logger.info(f"🚀 Iniciando despliegue de Fase 2: {phase['name']}")
    
    # Crear Redis si es necesario
    if not redis_host and phase.get("redis", False):
        success, redis_host = create_redis_instance()
        if not success:
            logger.error("❌ No se pudo crear instancia de Redis")
            return False
    
    # Construir y subir imagen
    success = build_and_push_image(
        image_name=phase["image"],
        dockerfile=phase["dockerfile"]
    )
    
    if not success:
        return False
    
    # Preparar variables de entorno
    env_vars = {}
    if redis_host:
        env_vars["REDIS_HOST"] = redis_host
        env_vars["REDIS_PORT"] = "6379"
    
    # Desplegar en Cloud Run
    success, _ = deploy_to_cloud_run(
        service_name=phase["service"],
        image_name=phase["image"],
        memory=phase["memory"],
        cpu=phase["cpu"],
        min_instances=phase["min_instances"],
        max_instances=phase["max_instances"],
        timeout=phase["timeout"],
        env_vars=env_vars
    )
    
    return success

def deploy_phase3() -> bool:
    """
    Despliega la fase 3: Arquitectura dividida.
    
    Returns:
        True si el despliegue fue exitoso, False en caso contrario
    """
    phase = PHASES[3]
    logger.info(f"🚀 Iniciando despliegue de Fase 3: {phase['name']}")
    
    # Desplegar servicios en orden
    for service_config in phase["services"]:
        logger.info(f"🔧 Desplegando {service_config['name']}")
        
        # Construir y subir imagen
        success = build_and_push_image(
            image_name=service_config["image"],
            dockerfile=service_config["dockerfile"]
        )
        
        if not success:
            return False
        
        # Preparar variables de entorno
        env_vars = {}
        
        # Si este servicio depende de otro, obtener URL del servicio dependiente
        if "depends_on" in service_config:
            depends_on = service_config["depends_on"]
            url_cmd = [
                "gcloud", "run", "services", "describe", depends_on,
                "--platform", "managed", 
                "--region", REGION, 
                "--format", "value(status.url)"
            ]
            
            try:
                result = run_command(url_cmd)
                grpc_url = result.stdout.strip()
                if grpc_url:
                    env_vars["GRPC_SERVER_URL"] = grpc_url
            except Exception as e:
                logger.error(f"❌ Error obteniendo URL del servicio {depends_on}: {e}")
                return False
        
        # Desplegar en Cloud Run
        success, _ = deploy_to_cloud_run(
            service_name=service_config["service"],
            image_name=service_config["image"],
            memory=service_config["memory"],
            cpu=service_config["cpu"],
            min_instances=service_config["min_instances"],
            max_instances=service_config["max_instances"],
            timeout=service_config["timeout"],
            env_vars=env_vars
        )
        
        if not success:
            return False
    
    return True

def main():
    """Función principal del script de despliegue."""
    parser = argparse.ArgumentParser(description='Desplegar sistema de recomendaciones retail')
    parser.add_argument('phase', type=int, choices=[1, 2, 3], help='Fase de despliegue')
    parser.add_argument('--redis-host', help='Dirección IP de Redis (para fase 2)')
    parser.add_argument('--project-id', help=f'ID del proyecto GCP (predeterminado: {PROJECT_ID})')
    parser.add_argument('--region', help=f'Región GCP (predeterminado: {REGION})')
    args = parser.parse_args()
    
    # Actualizar configuración desde argumentos
    global PROJECT_ID, REGION
    if args.project_id:
        PROJECT_ID = args.project_id
    if args.region:
        REGION = args.region
    
    logger.info(f"🚀 Iniciando despliegue del sistema de recomendaciones retail")
    logger.info(f"  Proyecto: {PROJECT_ID}")
    logger.info(f"  Región: {REGION}")
    logger.info(f"  Fase: {args.phase}")
    
    # Verificar prerrequisitos
    if not check_prerequisites():
        return 1
    
    # Configurar gcloud
    if not configure_gcloud():
        return 1
    
    # Desplegar fase seleccionada
    try:
        if args.phase == 1:
            success = deploy_phase1()
        elif args.phase == 2:
            success = deploy_phase2(args.redis_host)
        elif args.phase == 3:
            success = deploy_phase3()
        else:
            logger.error(f"❌ Fase no válida: {args.phase}")
            return 1
        
        if success:
            logger.info(f"✅ Despliegue de Fase {args.phase} completado exitosamente")
            return 0
        else:
            logger.error(f"❌ Despliegue de Fase {args.phase} falló")
            return 1
    
    except Exception as e:
        logger.error(f"❌ Error durante el despliegue: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())
