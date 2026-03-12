#!/bin/bash

# Secret Detection Setup Script
# This script sets up all secret detection tools for the repository

set -e

echo "🔐 Setting up Secret Detection for Teal Agents"
echo "================================================"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "❌ Error: Not in a git repository root"
    echo "Please run this script from the repository root directory"
    exit 1
fi

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3 first"
    exit 1
fi

# Install pre-commit
echo ""
echo "📦 Installing pre-commit..."
pip install pre-commit detect-secrets

# Install pre-commit hooks
echo ""
echo "🔧 Installing pre-commit hooks..."
pre-commit install
pre-commit install --hook-type commit-msg

# Create initial secrets baseline
echo ""
echo "🔍 Creating initial secrets baseline..."
if [ -f ".secrets.baseline" ]; then
    echo "⚠️  .secrets.baseline already exists, backing up..."
    mv .secrets.baseline .secrets.baseline.backup
fi

detect-secrets scan --all-files \
    --exclude-files '\.git/.*' \
    --exclude-files '\.secrets\.baseline' \
    --exclude-files 'package-lock\.json' \
    --exclude-files '.*\.lock' \
    --exclude-files 'uv\.lock' \
    > .secrets.baseline

echo ""
echo "✅ Secrets baseline created"

# Check for existing .env files
echo ""
echo "🔍 Checking for .env files..."
if find . -name ".env" -type f 2>/dev/null | grep -q .; then
    echo "⚠️  Found .env files in repository:"
    find . -name ".env" -type f
    echo ""
    echo "These files should NOT be committed. They are already in .gitignore"
else
    echo "✅ No .env files found"
fi

# Create .env.example if it doesn't exist
if [ ! -f "src/sk-agents/.env.example" ]; then
    echo ""
    echo "📝 Creating .env.example template..."
    echo "Please review and update src/sk-agents/.env.example"
fi

# Test pre-commit hooks
echo ""
echo "🧪 Testing pre-commit hooks..."
if pre-commit run --all-files; then
    echo "✅ All pre-commit hooks passed"
else
    echo "⚠️  Some pre-commit hooks failed"
    echo "This is expected if there are existing issues"
    echo "Review the output above and fix any issues"
fi

# Summary
echo ""
echo "================================================"
echo "✅ Secret Detection Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Review .secrets.baseline: detect-secrets audit .secrets.baseline"
echo "2. Copy .env.example to .env and add your secrets"
echo "3. Test a commit to verify hooks are working"
echo "4. Read SECURITY_SECRETS.md for full documentation"
echo ""
echo "Pre-commit hooks will now run automatically before each commit."
echo "To manually run checks: pre-commit run --all-files"
echo ""
