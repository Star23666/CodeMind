$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
docker compose -f docker-compose.yml -f compose.local.yaml stop
if ($LASTEXITCODE -ne 0) { throw 'CodeMind 停止失败。' }
