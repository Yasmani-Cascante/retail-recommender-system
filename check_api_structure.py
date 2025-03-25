"""
Script para verificar la estructura de la biblioteca google-cloud-retail
"""
import pkg_resources
import google.cloud.retail_v2
import inspect

try:
    # Obtener la versión instalada
    version = pkg_resources.get_distribution("google-cloud-retail").version
    print(f"Versión de google-cloud-retail: {version}")
    
    # Verificar ReconciliationMode
    reconciliation_modes = None
    if hasattr(google.cloud.retail_v2, "ImportProductsRequest"):
        import_request_class = google.cloud.retail_v2.ImportProductsRequest
        if hasattr(import_request_class, "ReconciliationMode"):
            reconciliation_modes = import_request_class.ReconciliationMode
            print("\nValores de ReconciliationMode:")
            for name, value in import_request_class.ReconciliationMode.__dict__.items():
                if not name.startswith('_'):
                    print(f"- {name}: {value}")
        else:
            print("\nImportProductsRequest no tiene un atributo ReconciliationMode")
    
    # Verificar ProductInlineSource
    print("\nEstructura de ProductInlineSource:")
    if hasattr(google.cloud.retail_v2, "ProductInlineSource"):
        product_inline_source = google.cloud.retail_v2.ProductInlineSource
        print(f"- Class: {product_inline_source}")
        print(f"- Campos: {dir(product_inline_source)}")
    else:
        print("ProductInlineSource no está disponible")
    
    # Verificar ImportProductsInputConfig
    print("\nEstructura de ImportProductsInputConfig:")
    if hasattr(google.cloud.retail_v2, "ImportProductsInputConfig"):
        import_config = google.cloud.retail_v2.ImportProductsInputConfig
        print(f"- Class: {import_config}")
        print(f"- Campos: {dir(import_config)}")
    else:
        print("ImportProductsInputConfig no está disponible")
    
    # Verificar si podemos construir las solicitudes correctas
    print("\nIntentando construir una solicitud de importación:")
    try:
        # Crear un producto de prueba
        product = google.cloud.retail_v2.Product(
            id="test_product",
            title="Test Product",
            availability="IN_STOCK"
        )
        
        # Crear ProductInlineSource
        product_inline_source = google.cloud.retail_v2.ProductInlineSource(products=[product])
        print("✓ ProductInlineSource creado correctamente")
        
        # Crear ImportProductsInputConfig
        input_config = google.cloud.retail_v2.ImportProductsInputConfig(
            product_inline_source=product_inline_source
        )
        print("✓ ImportProductsInputConfig creado correctamente")
        
        # Crear ImportProductsRequest
        import_request = google.cloud.retail_v2.ImportProductsRequest(
            parent="projects/test/locations/global/catalogs/default_catalog/branches/default_branch",
            input_config=input_config,
            reconciliation_mode="INCREMENTAL"
        )
        print("✓ ImportProductsRequest creado correctamente")
        print(f"- Tipo: {type(import_request)}")
        print(f"- Campos: {dir(import_request)}")
        
    except Exception as e:
        print(f"✗ Error al construir la solicitud: {str(e)}")
        
except Exception as e:
    print(f"Error general: {str(e)}")
