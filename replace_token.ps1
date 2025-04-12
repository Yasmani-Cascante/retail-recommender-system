# Simple PowerShell script to replace Shopify access tokens
Write-Host "Replacing Shopify access tokens..."

# Files to process
$files = @(
    "deploy_tfidf_events_final.ps1",
    "deploy_tfidf_full_metrics.ps1",
    "deploy_tfidf_shopify.ps1",
    "deploy_tfidf_shopify.py",
    "deploy_tfidf_shopify_improved.ps1"
)

# Process each file
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Processing $file..."
        
        # Read file content
        $content = Get-Content -Path $file -Raw
        
        # Replace pattern
        $content = $content -replace "SHOPIFY_ACCESS_TOKEN=shpat_[a-zA-Z0-9]+", "SHOPIFY_ACCESS_TOKEN=`"REMOVED_FOR_SECURITY`""
        
        # Write back
        Set-Content -Path $file -Value $content -Encoding UTF8
        
        Write-Host "Processed $file"
    } else {
        Write-Host "File $file not found"
    }
}

Write-Host "Done!"
