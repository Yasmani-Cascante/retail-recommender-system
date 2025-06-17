import requests
import sys

def check_versions(requirements_file):
    print(f"Verificando dependencias en {requirements_file}...")
    with open(requirements_file) as f:
        for line in f:
            line = line.strip()
            # Saltar líneas de comentarios o vacías
            if not line or line.startswith('#') or '>=' in line:
                continue
                
            if '==' in line:
                package, version = line.split('==')
                try:
                    response = requests.get(f"https://pypi.org/pypi/{package}/json")
                    if response.status_code == 200:
                        releases = list(response.json()['releases'].keys())
                        if releases and version not in releases:
                            available = ", ".join(releases[-5:]) if len(releases) > 5 else ", ".join(releases)
                            print(f"⚠️ {package}=={version} no está disponible en PyPI.")
                            print(f"   Versiones disponibles (últimas 5): {available}")
                    else:
                        print(f"⚠️ No se pudo verificar {package}: Código {response.status_code}")
                except Exception as e:
                    print(f"⚠️ Error al verificar {package}: {e}")

if __name__ == "__main__":
    check_versions("requirements.txt")
    print("Verificación completada.")
