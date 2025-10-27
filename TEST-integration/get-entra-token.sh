#!/bin/bash
# Get Microsoft Entra ID token for testing

# Load credentials from .env.test
source .env.test

if [ -z "$TA_ENTRA_TENANT_ID" ] || [ -z "$TA_ENTRA_CLIENT_ID" ] || [ -z "$TA_ENTRA_CLIENT_SECRET" ]; then
    echo "❌ Entra credentials not set in .env.test"
    exit 1
fi

echo "🔐 Getting Entra ID token..."
echo "Tenant: $TA_ENTRA_TENANT_ID"
echo "Client: $TA_ENTRA_CLIENT_ID"
echo ""

# Get token using client credentials flow
# The scope should be for YOUR application, not Graph API
# Format: api://<client-id>/.default OR just <client-id>/.default
RESPONSE=$(curl -s -X POST \
  "https://login.microsoftonline.com/$TA_ENTRA_TENANT_ID/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=$TA_ENTRA_CLIENT_ID" \
  -d "client_secret=$TA_ENTRA_CLIENT_SECRET" \
  -d "scope=api://$TA_ENTRA_CLIENT_ID/.default" \
  -d "grant_type=client_credentials")

# Check if we got an access token
if echo "$RESPONSE" | grep -q "access_token"; then
    TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
    echo "✅ Token obtained successfully"
    echo ""
    echo "Token (first 50 chars): ${TOKEN:0:50}..."
    echo ""
    echo "Export this to use in tests:"
    echo "export ENTRA_TOKEN=\"$TOKEN\""
    echo ""
    echo "Or test directly:"
    echo "curl -X POST http://localhost:8000/integration-test-agent/1.0 \\"
    echo "  -H \"Authorization: Bearer \$TOKEN\" \\"
    echo "  -H \"Content-Type: application/json\" \\"
    echo "  -H \"X-API-Key: test-api-key-12345\" \\"
    echo "  -d '{\"items\": [{\"content_type\": \"text\", \"content\": \"Hello\"}]}'"
else
    echo "❌ Failed to get token"
    echo "Response: $RESPONSE"
fi

