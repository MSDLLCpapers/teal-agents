# Quick Reference: Preventing Secret Commits

## 🚀 Quick Start (New Developer)

```bash
# 1. Clone the repository
git clone <repo-url>
cd teal-agents

# 2. Run setup script
# On Windows:
.\setup-secret-detection.ps1

# On Linux/Mac:
chmod +x setup-secret-detection.sh
./setup-secret-detection.sh

# 3. Copy .env.example and add your secrets
cp src/sk-agents/.env.example src/sk-agents/.env
# Edit .env with your actual API keys
```

## ✅ Daily Workflow

### Before Committing
Pre-commit hooks run automatically, but you can run them manually:

```bash
# Check all files
pre-commit run --all-files

# Check only staged files
pre-commit run
```

### If Hook Fails
1. **Read the error message** - It shows what was detected
2. **Remove the secret** from your code
3. **Use environment variables** instead:
   ```python
   # ❌ Don't do this
   API_KEY = "sk-1234567890"

   # ✅ Do this
   import os
   API_KEY = os.getenv("TA_API_KEY")
   ```
4. **Try committing again**

## 🔍 Common Commands

### Check for Secrets
```bash
# Quick scan
gitleaks detect --source . -v

# Deep scan with history
gitleaks detect --source . --log-opts="--all"

# Scan with detect-secrets
detect-secrets scan --all-files
```

### Update Secrets Baseline
```bash
# Re-scan
detect-secrets scan --all-files > .secrets.baseline

# Audit findings
detect-secrets audit .secrets.baseline
```

### Skip Hooks (Emergency Only!)
```bash
# Skip pre-commit hooks
git commit --no-verify -m "message"

# ⚠️ WARNING: Only use in genuine emergencies
# CI/CD will still catch secrets
```

## 📋 Checklist for Pull Requests

Before submitting a PR:

- [ ] No secrets in code (use environment variables)
- [ ] `.env` file is not committed (it's gitignored)
- [ ] `.env.example` is updated if you added new variables
- [ ] Pre-commit hooks passed
- [ ] All tests pass
- [ ] Secret scanning workflow passed in GitHub Actions

## 🆘 I Committed a Secret! What Now?

### Step 1: Revoke the Secret Immediately
- Generate a new API key
- Invalidate the old one
- Update your `.env` file

### Step 2: Remove from Git History

**If not pushed yet:**
```bash
# Undo last commit
git reset HEAD~1

# Remove secret and commit again
# Edit files to remove secret
git add .
git commit -m "feat: add feature (secrets removed)"
```

**If already pushed:**
```bash
# Contact your team lead or DevSecOps
# May need to use git-filter-repo or BFG
# This rewrites history!
```

### Step 3: Notify Security Team
- Report the incident
- Document what was exposed
- Follow company security procedures

## 💡 Best Practices

### ✅ Do This
- Use `.env` files for secrets (gitignored)
- Use environment variables in code
- Use `.env.example` as a template
- Commit `.env.example` (without real secrets)
- Use Azure Key Vault for production
- Rotate keys regularly

### ❌ Don't Do This
- Hardcode API keys in code
- Commit `.env` files
- Put secrets in configuration files
- Share secrets in chat/email
- Use `--no-verify` routinely
- Ignore security warnings

## 📊 What Gets Scanned

### Local (Pre-commit)
- detect-secrets
- gitleaks
- detect-private-key

### CI/CD (GitHub Actions)
- Gitleaks
- detect-secrets
- TruffleHog
- GitHub Secret Scanning (if enabled)

### Detected Patterns
- API keys (OpenAI, Anthropic, Azure)
- Bearer tokens
- Private keys (SSH, TLS)
- Database credentials
- High-entropy strings
- JWT tokens

## 🔧 Troubleshooting

### Hook Takes Too Long
```bash
# Update pre-commit hooks
pre-commit autoupdate

# Clear cache
pre-commit clean
```

### False Positives
Add to `.gitleaks.toml`:
```toml
[allowlist]
regexes = [
    '''your-false-positive-pattern'''
]
```

### Hook Not Running
```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install
```

## 📚 More Information

- Full documentation: `SECURITY_SECRETS.md`
- Gitleaks config: `.gitleaks.toml`
- Pre-commit config: `.pre-commit-config.yaml`
- GitHub workflow: `.github/workflows/secret-scanning.yaml`

## 🎯 Key Takeaways

1. **Never hardcode secrets** - Use environment variables
2. **Never commit .env files** - They're gitignored for a reason
3. **Pre-commit hooks are your friend** - They prevent mistakes
4. **If you commit a secret, revoke it immediately** - Don't just delete it
5. **When in doubt, ask** - Security team is here to help

---

**Questions?** Check `SECURITY_SECRETS.md` or contact the DevSecOps team.
