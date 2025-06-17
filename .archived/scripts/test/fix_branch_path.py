"""
Este script modifica el archivo retail_api.py para utilizar la rama correcta (0) 
en lugar de "default_branch" según lo que vemos en la consola de Google Cloud.
"""
import re
import sys

def update_branch_path():
    try:
        # Ruta al archivo retail_api.py
        file_path = "src/recommenders/retail_api.py"
        
        # Leer el archivo
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Buscar y reemplazar la ruta de la rama
        # Cambiamos de /catalogs/{self.catalog}/branches/default_branch a /catalogs/{self.catalog}/branches/0
        updated_content = re.sub(
            r'f"projects/{self\.project_number}/locations/{self\.location}"\s*f"/catalogs/{self\.catalog}/branches/default_branch"',
            r'f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}/branches/0"',
            content
        )
        
        # Escribir el archivo modificado
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(updated_content)
        
        print(f"✅ Se actualizó correctamente la ruta de la rama en {file_path}")
        return True
    
    except Exception as e:
        print(f"❌ Error al actualizar el archivo: {str(e)}")
        return False

if __name__ == "__main__":
    update_branch_path()
