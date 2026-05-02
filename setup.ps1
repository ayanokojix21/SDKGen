# PowerShell script to set up the environment
Write-Host "Setting up Docs-to-Code Backend Environment..." -ForegroundColor Cyan

# 1. Check Python installation
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# 2. Create virtual environment with uv
if (!(Test-Path ".venv")) {
    Write-Host "Creating virtual environment with uv..."
    uv venv .venv
}

# 3. Activate venv and install requirements with uv
Write-Host "Installing dependencies with uv..."
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. Install Playwright browsers
Write-Host "Installing Playwright Chromium..."
playwright install chromium

# 5. Check for .env file
if (!(Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Created .env file. Please edit it and add your GOOGLE_API_KEY." -ForegroundColor Yellow
}

Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "To start the server, run:" -ForegroundColor Cyan
Write-Host ".\.venv\Scripts\Activate.ps1"
Write-Host "uvicorn backend.main:app --reload"
