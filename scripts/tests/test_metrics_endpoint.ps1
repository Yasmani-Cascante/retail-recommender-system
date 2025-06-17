# Script para probar el endpoint de métricas

# Obtener la URL del servicio desplegado
$ServiceName = "retail-recommender-tfidf-metrics"
$Region = "us-central1"
$ServiceUrl = gcloud run services describe $ServiceName --platform managed --region $Region --format 'value(status.url)'

# Definir el endpoint de métricas
$MetricsUrl = "$ServiceUrl/v1/metrics"

# Definir los encabezados
$Headers = @{
    "X-API-Key" = "2fed9999056fab6dac5654238f0cae1c"
}

# Realizar algunas solicitudes de recomendaciones para generar métricas
$ProductIds = @("9978503037237", "9978480853301", "9978826752309")
$UserId = "test_metrics_user"

Write-Host "Realizando solicitudes de prueba para generar métricas..." -ForegroundColor Yellow

foreach ($ProductId in $ProductIds) {
    # Registrar un evento de vista
    $EventUrl = "$ServiceUrl/v1/events/user/$UserId`?event_type=detail-page-view&product_id=$ProductId"
    try {
        Invoke-RestMethod -Uri $EventUrl -Method Post -Headers $Headers | Out-Null
        Write-Host "✓ Evento de vista registrado para producto $ProductId" -ForegroundColor Green
    } catch {
        Write-Host "✗ Error registrando evento para producto $ProductId: $_" -ForegroundColor Red
    }
    
    # Solicitar recomendaciones para el producto
    $RecommendationUrl = "$ServiceUrl/v1/recommendations/$ProductId"
    try {
        Invoke-RestMethod -Uri $RecommendationUrl -Method Get -Headers $Headers | Out-Null
        Write-Host "✓ Recomendaciones solicitadas para producto $ProductId" -ForegroundColor Green
    } catch {
        Write-Host "✗ Error solicitando recomendaciones para producto $ProductId: $_" -ForegroundColor Red
    }
    
    # Pausa breve entre solicitudes
    Start-Sleep -Milliseconds 500
}

# Solicitar recomendaciones para el usuario
$UserRecommendationUrl = "$ServiceUrl/v1/recommendations/user/$UserId"
try {
    Invoke-RestMethod -Uri $UserRecommendationUrl -Method Get -Headers $Headers | Out-Null
    Write-Host "✓ Recomendaciones solicitadas para usuario $UserId" -ForegroundColor Green
} catch {
    Write-Host "✗ Error solicitando recomendaciones para usuario $UserId: $_" -ForegroundColor Red
}

# Consultar el endpoint de métricas
Write-Host "`nConsultando el endpoint de métricas..." -ForegroundColor Yellow
try {
    $Response = Invoke-RestMethod -Uri $MetricsUrl -Method Get -Headers $Headers
    
    Write-Host "`n=== Métricas del Sistema de Recomendaciones ===" -ForegroundColor Cyan
    Write-Host "Total de solicitudes: $($Response.realtime_metrics.total_requests)" -ForegroundColor White
    
    if ($Response.realtime_metrics.average_response_time_ms -ne $null) {
        $AvgTime = [math]::Round($Response.realtime_metrics.average_response_time_ms, 2)
        Write-Host "Tiempo promedio de respuesta: $AvgTime ms" -ForegroundColor White
    }
    
    if ($Response.realtime_metrics.fallback_rate -ne $null) {
        $FallbackRate = [math]::Round($Response.realtime_metrics.fallback_rate * 100, 2)
        Write-Host "Tasa de fallback: $FallbackRate%" -ForegroundColor White
    }
    
    Write-Host "`nDistribución de tipos de recomendación:" -ForegroundColor Cyan
    if ($Response.realtime_metrics.recommendation_type_distribution -ne $null) {
        foreach ($type in $Response.realtime_metrics.recommendation_type_distribution.PSObject.Properties) {
            $Percentage = [math]::Round($type.Value * 100, 2)
            Write-Host "  $($type.Name): $Percentage%" -ForegroundColor White
        }
    }
    
    Write-Host "`nCategorías más recomendadas:" -ForegroundColor Cyan
    if ($Response.realtime_metrics.top_10_category_distribution -ne $null) {
        foreach ($category in $Response.realtime_metrics.top_10_category_distribution.PSObject.Properties) {
            $Percentage = [math]::Round($category.Value * 100, 2)
            Write-Host "  $($category.Name): $Percentage%" -ForegroundColor White
        }
    }
} catch {
    Write-Host "Error consultando el endpoint de métricas: $_" -ForegroundColor Red
    
    # Mostrar la respuesta completa para diagnóstico
    try {
        $ErrorResponse = Invoke-WebRequest -Uri $MetricsUrl -Method Get -Headers $Headers -ErrorAction SilentlyContinue
        Write-Host "Código de estado: $($ErrorResponse.StatusCode)" -ForegroundColor Red
        Write-Host "Respuesta: $($ErrorResponse.Content)" -ForegroundColor Red
    } catch {
        Write-Host "No se pudo obtener más información sobre el error" -ForegroundColor Red
    }
}

Write-Host "`nURL del endpoint de métricas: $MetricsUrl" -ForegroundColor Cyan
Write-Host "Incluye el encabezado X-API-Key: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor Cyan
