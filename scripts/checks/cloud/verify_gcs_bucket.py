#!/usr/bin/env python3
"""
Script para verificar la configuración del bucket de GCS.
"""
import os
import logging
from dotenv import load_dotenv
from google.cloud import storage
from google.cloud.exceptions import NotFound

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

def verify_gcs_bucket():
    """Verifica que el bucket de GCS existe y tiene los permisos correctos."""
    try:
        # Obtener nombre del bucket
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            logging.error("GCS_BUCKET_NAME no está configurado en las variables de entorno")
            return False

        # Inicializar cliente de GCS
        logging.info(f"Verificando bucket: {bucket_name}")
        storage_client = storage.Client()
        
        # Verificar si el bucket existe
        try:
            bucket = storage_client.get_bucket(bucket_name)
            logging.info(f"✅ El bucket {bucket_name} existe")
        except NotFound:
            logging.error(f"❌ El bucket {bucket_name} no existe")
            logging.info("Para crear el bucket, ejecute:")
            logging.info(f"gcloud storage buckets create gs://{bucket_name} --location=<region> --project=<project_id>")
            return False
        
        # Realizar prueba de escritura
        try:
            blob = bucket.blob("test-permissions.txt")
            blob.upload_from_string("Test write permission")
            logging.info(f"✅ Prueba de escritura exitosa en el bucket {bucket_name}")
            
            # Eliminar archivo de prueba
            blob.delete()
            logging.info(f"✅ Prueba de eliminación exitosa en el bucket {bucket_name}")
        except Exception as e:
            logging.error(f"❌ Error al escribir en el bucket: {str(e)}")
            logging.info("Para otorgar permisos, ejecute:")
            logging.info(f"gcloud storage buckets add-iam-policy-binding gs://{bucket_name} --member=serviceAccount:<email> --role=roles/storage.objectAdmin")
            return False
        
        logging.info("✅ El bucket de GCS está correctamente configurado")
        return True
        
    except Exception as e:
        logging.error(f"Error al verificar el bucket de GCS: {str(e)}")
        return False

if __name__ == "__main__":
    verify_gcs_bucket()
