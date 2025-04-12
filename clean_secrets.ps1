# Script para limpiar secretos del historial de Git
# Este script te ayudará a eliminar secretos y credenciales sensibles de la historia de Git

Write-Host "====================================================================" -ForegroundColor Yellow
Write-Host "          HERRAMIENTA DE LIMPIEZA DE SECRETOS DE GIT" -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Este script te ayudará a eliminar secretos y credenciales sensibles" -ForegroundColor Cyan
Write-Host "del historial de Git, para que puedas hacer push sin que GitHub" -ForegroundColor Cyan
Write-Host "bloquee la operación debido a la detección de secretos." -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANTE: Este proceso modificará el historial de Git y requerirá" -ForegroundColor Red
Write-Host "un push forzado. Si estás colaborando con otros desarrolladores," -ForegroundColor Red
Write-Host "asegúrate de coordinar con ellos antes de ejecutar este script." -ForegroundColor Red
Write-Host ""

# Verificar si BFG Repo-Cleaner está instalado
$BfgExists = $false
try {
    $BfgVersion = java -jar bfg.jar --version 2>&1
    $BfgExists = $true
} catch {
    Write-Host "BFG Repo-Cleaner no está instalado o no es accesible." -ForegroundColor Yellow
    Write-Host "Vamos a usar un enfoque alternativo para limpiar los secretos." -ForegroundColor Yellow
}

# Función para reemplazar secretos en archivos
function Replace-Secret {
    param (
        [string]$FilePath,
        [string]$SecretPattern,
        [string]$Replacement
    )
    
    if (Test-Path $FilePath) {
        $content = Get-Content $FilePath -Raw
        
        if ($content -match $SecretPattern) {
            $newContent = $content -replace $SecretPattern, $Replacement
            Set-Content -Path $FilePath -Value $newContent
            return $true
        }
        return $false
    } else {
        Write-Host "El archivo $FilePath no existe." -ForegroundColor Yellow
        return $false
    }
}

# Lista de archivos con secretos y patrones a reemplazar
$FilesToClean = @(
    @{
        Path = "deploy_tfidf_events_final.ps1"
        Pattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
        Replacement = "SHOPIFY_ACCESS_TOKEN=`"REMOVED_FOR_SECURITY`""
    },
    @{
        Path = "deploy_tfidf_full_metrics.ps1"
        Pattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
        Replacement = "SHOPIFY_ACCESS_TOKEN=`"REMOVED_FOR_SECURITY`""
    },
    @{
        Path = "deploy_tfidf_shopify.ps1"
        Pattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
        Replacement = "SHOPIFY_ACCESS_TOKEN=`"REMOVED_FOR_SECURITY`""
    },
    @{
        Path = "deploy_tfidf_shopify.py"
        Pattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
        Replacement = "SHOPIFY_ACCESS_TOKEN=`"REMOVED_FOR_SECURITY`""
    },
    @{
        Path = "deploy_tfidf_shopify_improved.ps1"
        Pattern = "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+"
        Replacement = "SHOPIFY_ACCESS_TOKEN=`"REMOVED_FOR_SECURITY`""
    }
)

# Opción 1: Usar BFG si está disponible
if ($BfgExists) {
    Write-Host "Usando BFG Repo-Cleaner para eliminar secretos del historial..." -ForegroundColor Green
    
    # Crear un repositorio espejo para trabajar con BFG
    Write-Host "Creando un repositorio espejo..." -ForegroundColor Yellow
    git clone --mirror . repo-mirror.git
    
    # Cambiar al directorio del repositorio espejo
    Set-Location repo-mirror.git
    
    # Usar BFG para eliminar secretos
    Write-Host "Ejecutando BFG para eliminar secretos..." -ForegroundColor Yellow
    java -jar ../bfg.jar --replace-text ../replacements.txt
    
    # Limpiar y actualizar el repositorio
    Write-Host "Limpiando y actualizando el repositorio..." -ForegroundColor Yellow
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    
    # Volver al directorio original
    Set-Location ..
    
    Write-Host "BFG ha terminado de limpiar los secretos." -ForegroundColor Green
    Write-Host "Ahora necesitas actualizar tu repositorio local con estos cambios." -ForegroundColor Yellow
    
    # Preguntar si se quiere actualizar el repositorio local
    $UpdateLocal = Read-Host "¿Quieres actualizar tu repositorio local con estos cambios? (S/N)"
    if ($UpdateLocal -eq "S" -or $UpdateLocal -eq "s") {
        Write-Host "Actualizando repositorio local..." -ForegroundColor Yellow
        
        # Guardar el estado actual (stash)
        git stash
        
        # Forzar actualización desde el repositorio espejo
        git fetch repo-mirror.git refs/heads/*:refs/heads/*
        
        # Aplicar stash
        git stash pop
        
        Write-Host "Repositorio local actualizado. Ahora puedes hacer push forzado." -ForegroundColor Green
    }
    
    Write-Host "Para completar el proceso, debes hacer un push forzado:" -ForegroundColor Yellow
    Write-Host "git push --force" -ForegroundColor Cyan
} 
# Opción 2: Solución manual si BFG no está disponible
else {
    Write-Host "Iniciando limpieza manual de archivos con secretos..." -ForegroundColor Green
    
    $FilesCleared = 0
    foreach ($FileInfo in $FilesToClean) {
        Write-Host "Procesando $($FileInfo.Path)..." -ForegroundColor Yellow
        $Result = Replace-Secret -FilePath $FileInfo.Path -SecretPattern $FileInfo.Pattern -Replacement $FileInfo.Replacement
        
        if ($Result) {
            Write-Host "  ✅ Secretos reemplazados exitosamente en $($FileInfo.Path)" -ForegroundColor Green
            $FilesCleared++
        } else {
            Write-Host "  ℹ️ No se encontraron coincidencias del patrón de secretos en $($FileInfo.Path)" -ForegroundColor Cyan
        }
    }
    
    Write-Host ""
    Write-Host "Se han limpiado $FilesCleared archivos." -ForegroundColor Green
    Write-Host ""
    Write-Host "IMPORTANTE: Esta limpieza solo afecta a los archivos locales, pero los secretos" -ForegroundColor Yellow
    Write-Host "todavía están en el historial de Git. Para una solución completa, necesitas:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Crear un nuevo commit con estos cambios:" -ForegroundColor Cyan
    Write-Host "   git add -A" -ForegroundColor White
    Write-Host "   git commit -m \"Removed sensitive information\"" -ForegroundColor White
    Write-Host ""
    Write-Host "2. Desbloquear el push en GitHub siguiendo el enlace que te proporciona" -ForegroundColor Cyan
    Write-Host "   cuando intentas hacer push, o revisar y aprobar el push bloqueado" -ForegroundColor Cyan
    Write-Host "   en la configuración de seguridad del repositorio." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "3. Hacer push de tus cambios:" -ForegroundColor Cyan
    Write-Host "   git push" -ForegroundColor White
    Write-Host ""
    Write-Host "Para una solución más completa que elimine los secretos del historial," -ForegroundColor Yellow
    Write-Host "te recomendamos utilizar BFG Repo-Cleaner:" -ForegroundColor Yellow
    Write-Host "https://rtyley.github.io/bfg-repo-cleaner/" -ForegroundColor White
}

Write-Host ""
Write-Host "====================================================================" -ForegroundColor Yellow
Write-Host "                 SIGUIENTE PASO IMPORTANTE" -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Yellow
Write-Host "Asegúrate de actualizar tu archivo .env.secrets con las credenciales correctas:" -ForegroundColor Cyan
Write-Host ""
Write-Host "GOOGLE_PROJECT_NUMBER=178362262166" -ForegroundColor White
Write-Host "API_KEY=2fed9999056fab6dac5654238f0cae1c" -ForegroundColor White
Write-Host "SHOPIFY_SHOP_URL=ai-shoppings.myshopify.com" -ForegroundColor White
Write-Host "SHOPIFY_ACCESS_TOKEN=[tu token de acceso real]" -ForegroundColor White
Write-Host "GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild" -ForegroundColor White
Write-Host ""
Write-Host "El archivo .env.secrets está configurado para ser ignorado por Git," -ForegroundColor Yellow
Write-Host "por lo que no se subirá al repositorio y tus secretos estarán seguros." -ForegroundColor Yellow
