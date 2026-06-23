# Secret Detection and Prevention

This repository implements multiple layers of secret detection to prevent API keys, tokens, and other sensitive information from being committed.

## 🛡️ Protection Layers

### 1. Pre-commit Hooks (Local)
Pre-commit hooks run automatically before each commit to catch secrets before they enter version control.

**Tools Used:**
- **detect-secrets** - Baseline secret detection
- **gitleaks** - Advanced pattern matching for secrets
- **detect-private-key** - Finds SSH/TLS private keys

### 2. GitHub Actions (CI/CD)
Automated scanning on every push and pull request.

**Tools Used:**
- **Gitleaks** - Comprehensive secret scanning
- **detect-secrets** - Baseline comparison
- **TruffleHog** - High-entropy string detection

### 3. GitHub Push Protection (Repository Setting)
GitHub's native secret scanning with push protection (requires GitHub Advanced Security).

## 🚀 Setup Instructions

### Initial Setup

1. **Install pre-commit:**
   ```bash
   pip install pre-commit
   ```

2. **Install the git hooks:**
   ```bash
   cd <repository-root>
   pre-commit install
   ```

3. **Create initial secrets baseline:**
   ```bash
   detect-secrets scan --all-files \
     --exclude-files '\.git/.*' \
     --exclude-files '\.secrets\.baseline' \
     --exclude-files 'package-lock\.json' \
     > .secrets.baseline
   ```

4. **Verify installation:**
   ```bash
   pre-commit run --all-files
   ```

### For Existing Repositories with Secrets

If you need to audit existing secrets in the baseline:

```bash
detect-secrets audit .secrets.baseline
```

This opens an interactive session to mark findings as true/false positives.

## 🔍 What Gets Detected

### API Keys and Tokens
- OpenAI API keys (`sk-...`)
- Anthropic API keys (`sk-ant-...`)
- Azure keys
- Generic API keys
- Bearer tokens
- JWT tokens

### Credentials
- Passwords in configuration files
- Database connection strings
- Private keys (SSH, TLS, RSA)
- AWS credentials
- OAuth tokens

### High-Entropy Strings
- Base64 encoded secrets
- Hex-encoded secrets
- Random high-entropy strings that might be keys

## 📝 Best Practices

### 1. Use Environment Variables
Never hardcode secrets in code:

```python
# ❌ BAD
api_key = "sk-1234567890abcdef"

# ✅ GOOD
import os
api_key = os.getenv("API_KEY")
```

### 2. Use .env Files (Gitignored)
Store secrets in `.env` files that are already in `.gitignore`:

```bash
# .env (already in .gitignore)
API_KEY=your-secret-key
BASE_URL=https://api.example.com
```

### 3. Use Azure Key Vault or Similar
For production, use proper secret management:
- Azure Key Vault
- AWS Secrets Manager
- HashiCorp Vault

### 4. Use Example/Template Files
Provide template files without real secrets:

```bash
# .env.example (committed to repo)
API_KEY=your-api-key-here
BASE_URL=https://api.example.com

# .env (gitignored, contains real secrets)
API_KEY=sk-actual-secret-key
BASE_URL=https://api.example.com
```

## 🚨 What to Do If You Committed a Secret

### 1. Immediate Actions
If you accidentally committed a secret:

1. **Revoke/Rotate the secret immediately**
   - Generate a new API key
   - Invalidate the old one
   - Update your local `.env` file

2. **DO NOT just delete it in a new commit**
   - The secret is still in git history
   - Anyone with access can still see it

### 2. Clean Git History

**Option A: For recent commits (not pushed)**
```bash
# Undo the last commit, keeping changes
git reset HEAD~1

# Remove the secret from files
# ... edit your files ...

# Commit again
git add .
git commit -m "feat: add feature (secrets removed)"
```

**Option B: For pushed commits**
```bash
# Use BFG Repo-Cleaner or git-filter-repo
# This rewrites history - coordinate with team!

# Example with BFG:
bfg --replace-text secrets.txt
git push --force
```

**Option C: Contact Security Team**
- If unsure, contact your security team
- They may need to rotate organization-wide credentials

## ⚙️ Configuration Files

### `.gitleaks.toml`
Custom rules for detecting secrets. Add patterns specific to your organization:

```toml
[[rules]]
id = "custom-api-key"
description = "Custom API Key Pattern"
regex = '''your-pattern-here'''
tags = ["key", "api"]
```

### `.secrets.baseline`
Baseline of known secrets/false positives. Update when you have legitimate high-entropy strings:

```bash
# Re-scan and update baseline
detect-secrets scan --all-files > .secrets.baseline

# Audit to mark false positives
detect-secrets audit .secrets.baseline
```

### `.pre-commit-config.yaml`
Pre-commit hook configuration. Already set up with secret detection tools.

## 🧪 Testing

### Test Pre-commit Hooks
```bash
# Test on all files
pre-commit run --all-files

# Test on staged files only
pre-commit run

# Test specific hook
pre-commit run detect-secrets
pre-commit run gitleaks
```

### Test Locally Before Pushing
```bash
# Run gitleaks manually
gitleaks detect --source . --config .gitleaks.toml

# Run detect-secrets manually
detect-secrets scan --all-files
```

## 🔧 Troubleshooting

### Pre-commit Hook Failing
If a hook fails:

1. **Check the error message** - It will show what was detected
2. **Remove the secret** from your files
3. **Update .env or use environment variables**
4. **Try committing again**

### False Positives
If legitimate code is flagged:

1. **Add to allowlist** in `.gitleaks.toml`:
   ```toml
   [allowlist]
   regexes = [
       '''example-pattern-to-allow'''
   ]
   ```

2. **Update detect-secrets baseline:**
   ```bash
   detect-secrets audit .secrets.baseline
   ```

### Bypassing Hooks (Emergency Only)
```bash
# Skip pre-commit hooks (NOT RECOMMENDED)
git commit --no-verify -m "message"
```

⚠️ **Warning:** Only use `--no-verify` in genuine emergencies. CI/CD will still catch secrets.

## 📊 Monitoring

### GitHub Actions
- Check the "Actions" tab in GitHub for secret scanning results
- Failed checks will block PR merges
- Review the logs to see what was detected

### Regular Audits
Run periodic scans on the entire repository:

```bash
# Full repository scan
gitleaks detect --source . --verbose

# Scan with history
gitleaks detect --source . --log-opts="--all"
```

## 🔐 Additional Security Measures

1. **Enable GitHub Secret Scanning**
   - Settings → Security → Code security and analysis
   - Enable "Secret scanning"
   - Enable "Push protection"

2. **Use Branch Protection Rules**
   - Require PR reviews
   - Require status checks (including secret scanning)
   - Restrict who can push to main/master

3. **Regular Key Rotation**
   - Rotate API keys regularly (e.g., every 90 days)
   - Document rotation procedures
   - Test after rotation

4. **Audit Logging**
   - Monitor access to secrets
   - Review audit logs regularly
   - Set up alerts for suspicious activity

## 📚 Resources

- [Gitleaks Documentation](https://github.com/gitleaks/gitleaks)
- [detect-secrets Documentation](https://github.com/Yelp/detect-secrets)
- [TruffleHog Documentation](https://github.com/trufflesecurity/trufflehog)
- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [Pre-commit Framework](https://pre-commit.com/)

## 🆘 Support

If you have questions or need help:
1. Check this README
2. Review the tool documentation (links above)
3. Contact the DevSecOps team
4. Open an issue in this repository

---

**Remember:** Prevention is better than remediation. Always think twice before committing configuration files or adding new API integrations.
