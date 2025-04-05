#!/usr/bin/env python3
"""
Script de despliegue para la versión simplificada con TF-IDF.

Este script implementa el despliegue del sistema de recomendaciones
utilizando el recomendador TF-IDF, que no depende de modelos transformer.
"""

import os
import sys
import subprocess
import logging
from datetime import datetime

# Configurar logging
log_filename = f"deploy_tfidf_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
SERVICE_NAME = "retail-recommender-tfidf"
IMAGE_NAME = f"gcr.io/{PROJECT_ID}/retail-recommender-tfidf:latest"
DOCKERFILE = "Dockerfile.tfidf"

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
    
    # Construir comando de despliegue
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

def main():
    """Función principal del script de despliegue."""
    logger.info(f"Iniciando despliegue del sistema de recomendaciones TF-IDF")
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
    
    logger.info("✅ Despliegue completado exitosamente")
    return 0

if __name__ == "__main__":
    sys.exit(main())
