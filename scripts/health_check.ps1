param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$Port/api/v1"
$live = Invoke-RestMethod -Uri "$base/health/live" -Method Get -TimeoutSec 5
$ready = Invoke-RestMethod -Uri "$base/health/ready" -Method Get -TimeoutSec 5
[ordered]@{ live = $live.data; ready = $ready.data } | ConvertTo-Json -Depth 5
