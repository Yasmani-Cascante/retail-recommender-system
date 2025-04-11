import re
import os

def replace_endpoint():
    # Leer el archivo original
    main_file_path = os.path.join('src', 'api', 'main_tfidf_shopify_with_metrics.py')
    
    with open(main_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Leer el nuevo endpoint
    with open('updated_endpoint.py', 'r', encoding='utf-8') as f:
        new_endpoint = f.read()
    
    # Patrón para encontrar el endpoint de eventos
    pattern = r'@app\.post\("/v1/events/user/{user_id}"\)[^@]*?HTTPException\([^)]*\)\s*\)'
    
    # Reemplazar el endpoint
    updated_content = re.sub(pattern, new_endpoint, content, flags=re.DOTALL)
    
    # Guardar el archivo actualizado
    with open(main_file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"Endpoint actualizado en {main_file_path}")

if __name__ == "__main__":
    replace_endpoint()
