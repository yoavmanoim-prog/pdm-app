# ─────────────────────────────────────────────────────────────────────────────
# On-site installer for WINDOWS. The PowerShell equivalent of install.sh.
# Run on the factory server (Docker Desktop, Linux-container mode) AFTER
# unpacking the release tarball:
#
#   tar xzf pdm-onsite-<version>.tar.gz
#   cd pdm-onsite-<version>
#   .\install.ps1
#
# If PowerShell blocks the script, allow it for this session first:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# ─────────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host "==> Loading container images (docker load)..."
docker load -i images.tar

# First run: create .env from the template and stop so the operator can set
# secrets. Re-running install.ps1 after that proceeds to start the stack.
if (-not (Test-Path .env)) {
    Copy-Item .env.onsite.example .env
    # Pin the version that shipped in this bundle (replace the template's VERSION=).
    if (Test-Path .version) {
        $kept = Get-Content .env | Where-Object { $_ -notmatch '^VERSION=' }
        $version = Get-Content .version
        ($kept + $version) | Set-Content .env -Encoding ascii
    }
    Write-Host ""
    Write-Host "!!  Created .env from template. EDIT IT NOW and set strong values for:" -ForegroundColor Yellow
    Write-Host "      DB_PASSWORD, JWT_SECRET, BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD"
    Write-Host "    Tip (generate a JWT secret):  -join ((48..57)+(97..102) | Get-Random -Count 64 | % {[char]$_})"
    Write-Host "    Then re-run .\install.ps1 to start."
    exit 0
}

Write-Host "==> Starting the stack..."
# No build: run the images just loaded.
docker compose -f docker-compose.onsite.yml up -d

Write-Host ""
Write-Host "MechDocs is starting." -ForegroundColor Green
Write-Host "  Open:  http://<this-server-ip>/"
Write-Host "  Log in with the BOOTSTRAP_ADMIN_EMAIL / PASSWORD from .env, then change the password."
