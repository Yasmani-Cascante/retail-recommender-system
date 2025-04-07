#!/usr/bin/env python3
"""
Script de despliegue para la versión TF-IDF con conexión a Shopify.

Este script implementa el despliegue del sistema completo de recomendaciones
utilizando el recomendador TF-IDF, que no depende de modelos transformer,
y se conecta a Shopify para obtener datos reales de productos.
"""

import os
import sys
import subprocess
import logging
import json
from datetime import datetime

# Configurar logging
log_filename = f"deploy_tfidf_shopify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
SERVICE_NAME = "retail-recommender-tfidf-shopify"
IMAGE_NAME = f"gcr.io/{PROJECT_ID}/retail-recommender-tfidf-shopify:latest"
DOCKERFILE = "Dockerfile.tfidf.shopify"

# Variables de entorno para configuración del servicio
ENV_VARS = {
    "GOOGLE_PROJECT_NUMBER": os.environ.get("GOOGLE_PROJECT_NUMBER", "178362262166"),
    "GOOGLE_LOCATION": os.environ.get("GOOGLE_LOCATION", "global"),
    "GOOGLE_CATALOG": os.environ.get("GOOGLE_CATALOG", "default_catalog"),
    "GOOGLE_SERVING_CONFIG": os.environ.get("GOOGLE_SERVING_CONFIG", "default_recommendation_config"),
    "API_KEY": os.environ.get("API_KEY", "2fed9999056fab6dac5654238f0cae1c"),
    "SHOPIFY_SHOP_URL": os.environ.get("SHOPIFY_SHOP_URL", "ai-shoppings.myshopify.com"),
    "SHOPIFY_ACCESS_TOKEN": os.environ.get("SHOPIFY_ACCESS_TOKEN", "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"),
    "GCS_BUCKET_NAME": os.environ.get("GCS_BUCKET_NAME", "retail-recommendations-449216_cloudbuild"),
    "USE_GCS_IMPORT": "true",
    "DEBUG": os.environ.get("DEBUG", "true")
}

def run_command(cmd):
    """Ejecuta un comando del sistema y registra su salida."""
    logger.info(f"Ejecutando: {' '.join(cmd)}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    
    if stdout:
        for line in stdout.strip().split('\n'):
            logger.info(f"STDOUT: {line}")
    
    if stderr:
        for line in stderr.strip().split('\n'):
            if process.returncode != 0:
                logger.error(f"STDERR: {line}")
            else:
                logger.warning(f"STDERR: {line}")
    
    if process.returncode != 0:
        logger.error(f"Comando falló con código: {process.returncode}")
        return False
    
    return True

def build_and_push_image():
    """Construye y sube la imagen Docker a Google Container Registry."""
    logger.info(f"Construyendo imagen Docker: {IMAGE_NAME}")
    
    # Construir imagen
    success = run_command([
        "docker", "build", 
        "-t", IMAGE_NAME,
        "-f", DOCKERFILE,
        "."
    ])
    
    if not success:
        return False
    
    # Subir imagen a GCR
    logger.info(f"Subiendo imagen a Google Container Registry")
    success = run_command([
        "docker", "push",
        IMAGE_NAME
    ])
    
    return success

def deploy_to_cloud_run():
    """Despliega la imagen en Google Cloud Run."""
    logger.info(f"Desplegando en Cloud Run: {SERVICE_NAME}")
    
    # Construir comando base de despliegue
    deploy_cmd = [
        "gcloud", "run", "deploy", SERVICE_NAME,
        "--image", IMAGE_NAME,
        "--platform", "managed",
        "--region", REGION,
        "--memory", "1Gi",
        "--cpu", "1",
        "--min-instances", "0",
        "--max-instances", "10",
        "--allow-unauthenticated"
    ]
    
    # Agregar variables de entorno
    env_vars_str = ",".join([f"{k}={v}" for k, v in ENV_VARS.items()])
    deploy_cmd.extend(["--set-env-vars", env_vars_str])
    
    # Ejecutar despliegue
    success = run_command(deploy_cmd)
    
    if not success:
        return False
    
    # Obtener URL del servicio
    url_cmd = [
        "gcloud", "run", "services", "describe", SERVICE_NAME,
        "--platform", "managed", 
        "--region", REGION, 
        "--format", "value(status.url)"
    ]
    
    process = subprocess.Popen(
        url_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    
    if stdout:
        service_url = stdout.strip()
        logger.info(f"Servicio desplegado en: {service_url}")
    
    return True

def verify_deployment():
    """Verifica que el despliegue funciona correctamente."""
    logger.info("Verificando el despliegue...")
    
    # Obtener URL del servicio
    url_cmd = [
        "gcloud", "run", "services", "describe", SERVICE_NAME,
        "--platform", "managed", 
        "--region", REGION, 
        "--format", "value(status.url)"
    ]
    
    process = subprocess.Popen(
        url_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    
    if not stdout:
        logger.error("No se pudo obtener la URL del servicio")
        return False
    
    service_url = stdout.strip()
    
    # Verificar endpoint health
    import requests
    import time
    
    # Esperar un momento para que el servicio se inicialice
    logger.info("Esperando 10 segundos para que el servicio se inicialice...")
    time.sleep(10)
    
    # Verificar endpoint health
    health_url = f"{service_url}/health"
    logger.info(f"Verificando endpoint de salud: {health_url}")
    
    try:
        response = requests.get(health_url, timeout=30)
        if response.status_code == 200:
            logger.info("✅ Endpoint de salud responde correctamente")
            health_data = response.json()
            logger.info(f"Estado del servicio: {health_data.get('status', 'desconocido')}")
            return True
        else:
            logger.error(f"❌ Endpoint de salud devolvió código de estado: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Error verificando endpoint de salud: {str(e)}")
        return False

def get_current_env_vars():
    """Obtiene las variables de entorno actuales del servicio."""
    env_cmd = [
        "gcloud", "run", "services", "describe", SERVICE_NAME,
        "--platform", "managed", 
        "--region", REGION, 
        "--format", "json"
    ]
    
    process = subprocess.Popen(
        env_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    
    if process.returncode != 0 or not stdout:
        logger.warning("No se pudieron obtener las variables de entorno actuales")
        return {}
    
    try:
        service_data = json.loads(stdout)
        env_vars = {}
        
        if "spec" in service_data and "template" in service_data["spec"] and "containers" in service_data["spec"]["template"]:
            containers = service_data["spec"]["template"]["containers"]
            if containers and "env" in containers[0]:
                for env in containers[0]["env"]:
                    if "name" in env and "value" in env:
                        env_vars[env["name"]] = env["value"]
        
        return env_vars
    except Exception as e:
        logger.error(f"Error procesando datos del servicio: {str(e)}")
        return {}

def main():
    """Función principal del script de despliegue."""
    logger.info(f"Iniciando despliegue del sistema de recomendaciones TF-IDF con conexión a Shopify")
    logger.info(f"  Proyecto: {PROJECT_ID}")
    logger.info(f"  Región: {REGION}")
    logger.info(f"  Servicio: {SERVICE_NAME}")
    
    # Verificar que gcloud está configurado
    logger.info("Verificando configuración de gcloud...")
    success = run_command([
        "gcloud", "config", "get-value", "project"
    ])
    
    if not success:
        logger.error("Error verificando configuración de gcloud")
        return 1
    
    # Configurar proyecto y región
    logger.info(f"Configurando proyecto: {PROJECT_ID}")
    success = run_command([
        "gcloud", "config", "set", "project", PROJECT_ID
    ])
    
    if not success:
        logger.error(f"Error configurando proyecto: {PROJECT_ID}")
        return 1
    
    logger.info(f"Configurando región: {REGION}")
    success = run_command([
        "gcloud", "config", "set", "run/region", REGION
    ])
    
    if not success:
        logger.error(f"Error configurando región: {REGION}")
        return 1
    
    # Obtener variables de entorno actuales (si el servicio ya existe)
    current_env_vars = get_current_env_vars()
    if current_env_vars:
        logger.info(f"El servicio ya existe con {len(current_env_vars)} variables de entorno")
        # Actualizar variables de entorno con valores actuales (si existen)
        for key, value in current_env_vars.items():
            if key in ENV_VARS:
                logger.info(f"Manteniendo variable existente: {key}")
            else:
                ENV_VARS[key] = value
                logger.info(f"Agregando variable existente: {key}")
    
    # Construir y subir imagen
    logger.info("Construyendo y subiendo imagen Docker...")
    if not build_and_push_image():
        logger.error("Error construyendo o subiendo imagen Docker")
        return 1
    
    # Desplegar en Cloud Run
    logger.info("Desplegando en Cloud Run...")
    if not deploy_to_cloud_run():
        logger.error("Error desplegando en Cloud Run")
        return 1
    
    # Verificar despliegue
    logger.info("Verificando despliegue...")
    if not verify_deployment():
        logger.warning("⚠️ La verificación del despliegue falló, pero el servicio podría estar funcionando")
    
    logger.info("✅ Despliegue completado exitosamente")
    logger.info("La API estará disponible en unos minutos en la URL proporcionada arriba")
    return 0

if __name__ == "__main__":
    sys.exit(main())
