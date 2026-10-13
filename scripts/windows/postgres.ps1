# V-Base - local PostgreSQL development database (Docker).
#
# V-Base needs PostgreSQL; there is no SQLite fallback. This script starts a
# throwaway container that matches the DSN in backend/.env.example:
#
#   postgresql+asyncpg://vbase:vbase_dev_pw@127.0.0.1:5433/vbase
#
# Port 5433 is used deliberately so it never clashes with an existing local
# PostgreSQL install on the default 5432. The container keeps its data in a
# named volume, so stopping it does not lose your data.
#
# Usage:
#   scripts\windows\postgres.bat            # start (create on first run)
#   scripts\windows\postgres.bat stop       # stop, keep data
#   scripts\windows\postgres.bat destroy    # stop and DELETE all data
param(
    [ValidateSet("start", "stop", "destroy", "logs")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$name = "vbase-pg"
$volume = "vbase-pgdata"
$port = 5433

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker was not found. Install Docker Desktop, or point DATABASE_URL in backend\.env at your own PostgreSQL instance."
    exit 1
}

switch ($Action) {
    "stop" {
        Write-Host "Stopping $name (data is kept in volume $volume) ..."
        docker stop $name 2>$null | Out-Null
        Write-Host "Stopped."
    }
    "destroy" {
        Write-Host "Removing container $name and deleting volume $volume ..." -ForegroundColor Yellow
        docker rm -f $name 2>$null | Out-Null
        docker volume rm $volume 2>$null | Out-Null
        Write-Host "All local database data was deleted."
    }
    "logs" {
        docker logs --tail 50 $name
    }
    "start" {
        $running = docker ps --filter "name=^/$name$" --format "{{.Names}}"
        if ($running -eq $name) {
            Write-Host "$name is already running on port $port." -ForegroundColor Green
            exit 0
        }

        $exists = docker ps -a --filter "name=^/$name$" --format "{{.Names}}"
        if ($exists -eq $name) {
            Write-Host "Starting existing container $name ..."
            docker start $name | Out-Null
        } else {
            Write-Host "Creating postgres:16-alpine as $name on port $port ..."
            docker run -d --name $name `
                -e POSTGRES_USER=vbase `
                -e POSTGRES_PASSWORD=vbase_dev_pw `
                -e POSTGRES_DB=vbase `
                -p "$($port):5432" `
                -v "$($volume):/var/lib/postgresql/data" `
                --health-cmd "pg_isready -U vbase -d vbase" `
                --health-interval 5s --health-timeout 5s --health-retries 20 `
                postgres:16-alpine | Out-Null
        }

        Write-Host "Waiting for PostgreSQL to accept connections ..."
        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            $status = docker inspect --format "{{.State.Health.Status}}" $name 2>$null
            if ($status -eq "healthy") { $ready = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $ready) {
            Write-Warning "PostgreSQL did not report healthy in 60s. Check: docker logs $name"
            exit 1
        }

        # pg_trgm powers the trigram fuzzy-match indexes. The initial migration
        # also creates it, but doing it here means a fresh database is ready
        # before the first migration run.
        Write-Host "Enabling the pg_trgm extension ..."
        docker exec $name psql -U vbase -d vbase -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" | Out-Null

        Write-Host "PostgreSQL is ready on 127.0.0.1:$port (database 'vbase')." -ForegroundColor Green
        Write-Host "Next: scripts\windows\migrate.bat"
    }
}
