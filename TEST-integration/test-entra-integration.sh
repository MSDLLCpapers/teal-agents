#!/bin/bash
# Complete Entra ID + Arcade Integration Test

echo "═══════════════════════════════════════════════════════════════"
echo "  ENTRA ID + ARCADE INTEGRATION TEST"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Step 1: Get Entra ID token with user claims
echo "📋 Step 1: Getting Entra ID Token"
echo "───────────────────────────────────────────────────────────────"
echo "Running device code flow..."
echo "You'll need to sign in with your Microsoft account."
echo ""

./get-user-token.sh

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Failed to get Entra ID token"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Did you enable 'Allow public client flows' in Azure Portal?"
    echo "  2. Did you add the 'access_as_user' scope?"
    echo "  3. Did you sign in when prompted?"
    echo ""
    exit 1
fi

echo ""
echo "✅ Entra ID token obtained!"
echo ""

# Extract the token from the output (this is a simplification)
# In practice, the script should save the token

echo "═══════════════════════════════════════════════════════════════"
echo "  Step 2: Testing with Real Entra Token"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Please copy the token from above and run:"
echo ""
echo "export ENTRA_TOKEN=\"<your-token>\""
echo ""
echo "curl -X POST http://localhost:8000/integration-test-agent/1.0 \\"
echo "  -H \"Authorization: Bearer \$ENTRA_TOKEN\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -H \"X-API-Key: test-key\" \\"
echo "  -d '{\"items\": [{\"content_type\": \"text\", \"content\": \"What tools do you have?\"}]}' | jq"
echo ""
echo "Expected:"
echo "  ✅ EntraAuthorizer validates JWT"
echo "  ✅ User email extracted from token"
echo "  ✅ MCP discovery for that user"
echo "  ✅ Arcade tools returned"
echo ""

