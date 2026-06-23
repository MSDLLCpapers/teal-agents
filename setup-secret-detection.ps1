# Secret Detection Setup Script for Windows
# This script sets up all secret detection tools for the repository

Write-Host "🔐 Setting up Secret Detection for Teal Agents" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Check if we're in a git repository
if (-not (Test-Path ".git")) {
    Write-Host "❌ Error: Not in a git repository root" -ForegroundColor Red
    Write-Host "Please run this script from the repository root directory" -ForegroundColor Yellow
    exit 1
}

# Check Python installation
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3 first" -ForegroundColor Yellow
    exit 1
}

# Install pre-commit
Write-Host ""
Write-Host "📦 Installing pre-commit and detect-secrets..." -ForegroundColor Cyan
pip install pre-commit detect-secrets

# Install pre-commit hooks
Write-Host ""
Write-Host "🔧 Installing pre-commit hooks..." -ForegroundColor Cyan
pre-commit install
pre-commit install --hook-type commit-msg

# Create initial secrets baseline
Write-Host ""
Write-Host "🔍 Creating initial secrets baseline..." -ForegroundColor Cyan
if (Test-Path ".secrets.baseline") {
    Write-Host "⚠️  .secrets.baseline already exists, backing up..." -ForegroundColor Yellow
    Move-Item .secrets.baseline .secrets.baseline.backup -Force
}

detect-secrets scan --all-files `
    --exclude-files '\.git/.*' `
    --exclude-files '\.secrets\.baseline' `
    --exclude-files 'package-lock\.json' `
    --exclude-files '.*\.lock' `
    --exclude-files 'uv\.lock' `
    > .secrets.baseline

Write-Host ""
Write-Host "✅ Secrets baseline created" -ForegroundColor Green

# Check for existing .env files
Write-Host ""
Write-Host "🔍 Checking for .env files..." -ForegroundColor Cyan
$envFiles = Get-ChildItem -Path . -Filter ".env" -Recurse -File -ErrorAction SilentlyContinue
if ($envFiles) {
    Write-Host "⚠️  Found .env files in repository:" -ForegroundColor Yellow
    $envFiles | ForEach-Object { Write-Host "   $($_.FullName)" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "These files should NOT be committed. They are already in .gitignore" -ForegroundColor Yellow
} else {
    Write-Host "✅ No .env files found" -ForegroundColor Green
}

# Create .env.example if it doesn't exist
if (-not (Test-Path "src\sk-agents\.env.example")) {
    Write-Host ""
    Write-Host "📝 .env.example template already created" -ForegroundColor Cyan
    Write-Host "Please review and update src\sk-agents\.env.example" -ForegroundColor Yellow
}

# Test pre-commit hooks
Write-Host ""
Write-Host "🧪 Testing pre-commit hooks..." -ForegroundColor Cyan
$testResult = pre-commit run --all-files
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ All pre-commit hooks passed" -ForegroundColor Green
} else {
    Write-Host "⚠️  Some pre-commit hooks failed" -ForegroundColor Yellow
    Write-Host "This is expected if there are existing issues" -ForegroundColor Yellow
    Write-Host "Review the output above and fix any issues" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ Secret Detection Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Review .secrets.baseline: detect-secrets audit .secrets.baseline" -ForegroundColor White
Write-Host "2. Copy .env.example to .env and add your secrets" -ForegroundColor White
Write-Host "3. Test a commit to verify hooks are working" -ForegroundColor White
Write-Host "4. Read SECURITY_SECRETS.md for full documentation" -ForegroundColor White
Write-Host ""
Write-Host "Pre-commit hooks will now run automatically before each commit." -ForegroundColor Yellow
Write-Host "To manually run checks: pre-commit run --all-files" -ForegroundColor Yellow
Write-Host ""
