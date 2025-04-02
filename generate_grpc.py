
import os
import sys
import subprocess
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_grpc_code():
    """
    Genera los archivos Python a partir del proto para gRPC.
    Requiere que protoc y grpcio-tools estén instalados.
    """
    # Verificar si el archivo proto existe
    proto_file = "recommendation_service.proto"
    if not os.path.exists(proto_file):
        logging.error(f"Archivo proto no encontrado: {proto_file}")
        return False
    
    # Instalar grpcio-tools si no está instalado
    try:
        import grpc_tools.protoc
        logging.info("grpcio-tools ya está instalado")
    except ImportError:
        logging.info("Instalando grpcio-tools...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio-tools"])
    
    # Generar archivos Python
    logging.info(f"Generando código Python a partir de {proto_file}...")
    
    # Comando para protoc
    protoc_command = [
        sys.executable,  # Python ejecutable
        "-m",
        "grpc_tools.protoc",
        f"--proto_path=.",
        f"--python_out=.",
        f"--grpc_python_out=.",
        proto_file
    ]
    
    # Ejecutar protoc
    try:
        subprocess.check_call(protoc_command)
        logging.info("Código gRPC generado correctamente")
        logging.info("NOTA: Los valores predeterminados (default) se deben manejar en el código, no en el proto")
        
        # Verificar que los archivos fueron creados
        pb2_file = proto_file.replace(".proto", "_pb2.py")
        pb2_grpc_file = proto_file.replace(".proto", "_pb2_grpc.py")
        
        if os.path.exists(pb2_file) and os.path.exists(pb2_grpc_file):
            logging.info(f"Archivos generados: {pb2_file}, {pb2_grpc_file}")
            return True
        else:
            logging.error("No se encontraron los archivos generados")
            return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Error ejecutando protoc: {e}")
        return False
    except Exception as e:
        logging.error(f"Error general: {e}")
        return False

if __name__ == "__main__":
    if generate_grpc_code():
        logging.info("✅ Generación de código gRPC completada correctamente")
    else:
        logging.error("❌ Error generando código gRPC")
        sys.exit(1)
