from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY", "default_key")  # Asegúrate de configurar esto en producción
api_key_header = APIKeyHeader(name="X-API-Key")

async def get_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Could not validate API key"
        )
    return api_key

def get_current_user(api_key: str = Depends(get_api_key)) -> Optional[str]:
    # Aquí podrías implementar lógica adicional de autenticación
    return "authenticated_user"