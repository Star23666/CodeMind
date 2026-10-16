$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
docker compose -f docker-compose.yml -f compose.local.yaml up -d
if ($LASTEXITCODE -ne 0) { throw 'CodeMind 启动失败，请检查 Docker Desktop 和命令输出。' }
Write-Host '访问 http://localhost:8084'
