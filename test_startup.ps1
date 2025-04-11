# test_startup_local.ps1
Write-Host "Verificando inicio de la aplicación localmente..." -ForegroundColor Green

# Limpiar contenedores anteriores
$ContainerName = "retail-recommender-test"
docker rm -f $ContainerName 2>$null

# Construir imagen de prueba
Write-Host "Construyendo imagen de Docker..." -ForegroundColor Yellow
docker build -t retail-recommender-test:local -f Dockerfile.fixed .

# Ejecutar el contenedor en modo prueba
Write-Host "Iniciando contenedor de prueba..." -ForegroundColor Yellow
docker run -d --name $ContainerName -p 8080:8080 -e OFFLINE_MODE=true retail-recommender-test:local

# Esperar a que el contenedor inicie
Write-Host "Esperando 10 segundos para que el contenedor inicie..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Verificar el estado de salud
try {
    $Response = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get -TimeoutSec 5
    Write-Host "Respuesta del health check:" -ForegroundColor Green
    $Response | ConvertTo-Json | Write-Host
    $Success = $true
} catch {
    Write-Host "Error al verificar health check: $_" -ForegroundColor Red
    $Success = $false
}

# Mostrar logs del contenedor
Write-Host "`nLogs del contenedor:" -ForegroundColor Yellow
docker logs $ContainerName

# Limpiar
docker rm -f $ContainerName 2>$null

if ($Success) {
    Write-Host "`n✅ La aplicación inicia correctamente!" -ForegroundColor Green
} else {
    Write-Host "`n❌ La aplicación falló al iniciar. Revisa los logs para ver el error." -ForegroundColor Red
}