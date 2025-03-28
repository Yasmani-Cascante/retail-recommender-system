#!/usr/bin/env python3
import os
import sys

# Verificar la versión específica de la biblioteca
try:
    import google.cloud.retail_v2
    print(f"Versión de google-cloud-retail: {google.cloud.retail_v2.__version__ if hasattr(google.cloud.retail_v2, '__version__') else 'No disponible'}")
    
    # Verificar las clases disponibles
    from google.cloud.retail_v2.types.import_config import GcsSource, ProductInputConfig
    print("✅ GcsSource y ProductInputConfig importados correctamente")
    
    # Verificar ReconciliationMode
    from google.cloud.retail_v2.types import ImportProductsRequest
    print(f"ReconciliationMode disponible: {hasattr(ImportProductsRequest, 'ReconciliationMode')}")
    
    if hasattr(ImportProductsRequest, 'ReconciliationMode'):
        modes = ImportProductsRequest.ReconciliationMode
        print(f"Valores: {[m.name for m in modes]}")
    else:
        print("❌ ReconciliationMode no está disponible como subclase de ImportProductsRequest")
    
except ImportError as e:
    print(f"❌ Error importando bibliotecas: {e}")
    sys.exit(1)
