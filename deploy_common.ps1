# Script común para funciones de despliegue
# Este archivo contiene funciones compartidas por todos los scripts de despliegue

# Este es un módulo PowerShell centralizado para gestionar secretos de forma segura
function Load-SecretVariables {
    <#
    .SYNOPSIS
    Carga variables secretas desde un archivo .env.secrets que no se sube al repositorio
    
    .DESCRIPTION
    Esta función carga las variables secretas desde un archivo .env.secrets
    y las hace disponibles como variables PowerShell.
    #>
    
    $SecretsFile = ".env.secrets"
    
    if (-not (Test-Path $SecretsFile)) {
        Write-Host "Archivo de secretos ($SecretsFile) no encontrado." -ForegroundColor Yellow
        Write-Host "Creando archivo de secretos de ejemplo..." -ForegroundColor Yellow
        
        @"
# Secretos para el sistema de recomendaciones
# Copia este archivo como .env.secrets y actualiza los valores

# Google Cloud Project
GOOGLE_PROJECT_NUMBER=your_project_number
API_KEY=your_api_key

# Shopify
SHOPIFY_SHOP_URL=your_shop_url
SHOPIFY_ACCESS_TOKEN=your_access_token

# Google Cloud Storage
GCS_BUCKET_NAME=your_bucket_name
"@ | Out-File -FilePath "$SecretsFile.example" -Encoding utf8
        
        Write-Host "❌ Por favor, crea el archivo $SecretsFile con tus secretos reales basándote en $SecretsFile.example" -ForegroundColor Red
        return $false
    }
    
    # Cargar variables del archivo .env.secrets
    $Secrets = @{}
    Get-Content $SecretsFile | ForEach-Object {
        if (-not [string]::IsNullOrWhiteSpace($_) -and -not $_.StartsWith("#")) {
            $Key, $Value = $_.Split('=', 2)
            if ($Key -and $Value) {
                $Secrets[$Key.Trim()] = $Value.Trim()
                # Crear variable PowerShell
                Set-Variable -Name $Key.Trim() -Value $Value.Trim() -Scope Script
            }
        }
    }
    
    # Verificar que las variables requeridas estén presentes
    $RequiredVars = @(
        "GOOGLE_PROJECT_NUMBER",
        "API_KEY",
        "SHOPIFY_SHOP_URL",
        "SHOPIFY_ACCESS_TOKEN",
        "GCS_BUCKET_NAME"
    )
    
    $MissingVars = $RequiredVars | Where-Object { -not $Secrets.ContainsKey($_) }
    
    if ($MissingVars.Count -gt 0) {
        Write-Host "❌ Faltan las siguientes variables requeridas en ${SecretsFile}:" -ForegroundColor Red
        foreach ($Var in $MissingVars) {
            Write-Host "   - $Var" -ForegroundColor Red
        }
        return $false
    }
    
    Write-Host "✅ Variables secretas cargadas correctamente desde $SecretsFile" -ForegroundColor Green
    return $true
}

function Get-EnvVarsString {
    <#
    .SYNOPSIS
    Genera la cadena de variables de entorno para Cloud Run
    
    .DESCRIPTION
    Esta función genera la cadena de variables de entorno para usar
    en el despliegue a Cloud Run, utilizando las variables cargadas
    desde el archivo de secretos.
    #>
    
    $EnvVars = @(
        "GOOGLE_PROJECT_NUMBER=$GOOGLE_PROJECT_NUMBER",
        "GOOGLE_LOCATION=global",
        "GOOGLE_CATALOG=default_catalog",
        "GOOGLE_SERVING_CONFIG=default_recommendation_config",
        "API_KEY=$API_KEY",
        "SHOPIFY_SHOP_URL=$SHOPIFY_SHOP_URL",
        "SHOPIFY_ACCESS_TOKEN=$SHOPIFY_ACCESS_TOKEN",
        "GCS_BUCKET_NAME=$GCS_BUCKET_NAME",
        "USE_GCS_IMPORT=true",
        "DEBUG=true",
        "METRICS_ENABLED=true",
        "EXCLUDE_SEEN_PRODUCTS=true"
    )
    
    return $EnvVars -join ","
}
