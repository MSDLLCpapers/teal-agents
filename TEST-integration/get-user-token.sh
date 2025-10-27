#!/bin/bash
# Get Microsoft Entra ID token with USER context (Device Code Flow)
# This will include user claims like email, preferred_username, etc.

# Load credentials from .env.test
source .env.test

if [ -z "$TA_ENTRA_TENANT_ID" ] || [ -z "$TA_ENTRA_CLIENT_ID" ]; then
    echo "❌ Entra credentials not set in .env.test"
    exit 1
fi

echo "═══════════════════════════════════════════════════════════════"
echo "    ENTRA ID - USER TOKEN (Device Code Flow)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Tenant: $TA_ENTRA_TENANT_ID"
echo "Client: $TA_ENTRA_CLIENT_ID"
echo ""

# Step 1: Initiate device code flow
echo "🔐 Step 1: Initiating device code flow..."
# Use delegated scope (access_as_user) instead of .default for user tokens
DEVICE_RESPONSE=$(curl -s -X POST \
  "https://login.microsoftonline.com/$TA_ENTRA_TENANT_ID/oauth2/v2.0/devicecode" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=$TA_ENTRA_CLIENT_ID" \
  -d "scope=api://$TA_ENTRA_CLIENT_ID/access_as_user openid profile email")

# Extract device code and user code
DEVICE_CODE=$(echo "$DEVICE_RESPONSE" | jq -r '.device_code')
USER_CODE=$(echo "$DEVICE_RESPONSE" | jq -r '.user_code')
VERIFICATION_URI=$(echo "$DEVICE_RESPONSE" | jq -r '.verification_uri')
EXPIRES_IN=$(echo "$DEVICE_RESPONSE" | jq -r '.expires_in')
INTERVAL=$(echo "$DEVICE_RESPONSE" | jq -r '.interval')
MESSAGE=$(echo "$DEVICE_RESPONSE" | jq -r '.message')

if [ "$DEVICE_CODE" = "null" ]; then
    echo "❌ Failed to initiate device code flow"
    echo "Response: $DEVICE_RESPONSE"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "    ACTION REQUIRED - Please authenticate"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "$MESSAGE"
echo ""
echo "Or manually:"
echo "  1. Go to: $VERIFICATION_URI"
echo "  2. Enter code: $USER_CODE"
echo "  3. Sign in with your Microsoft account"
echo ""
echo "Waiting for authentication (expires in ${EXPIRES_IN}s)..."
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Step 2: Poll for token
MAX_ATTEMPTS=$((EXPIRES_IN / INTERVAL))
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    sleep $INTERVAL
    ATTEMPT=$((ATTEMPT + 1))
    
    echo "⏳ Checking authentication status (attempt $ATTEMPT/$MAX_ATTEMPTS)..."
    
    # Build token request (include client_secret if available for confidential clients)
    TOKEN_REQUEST="grant_type=urn:ietf:params:oauth:grant-type:device_code&client_id=$TA_ENTRA_CLIENT_ID&device_code=$DEVICE_CODE"
    if [ -n "$TA_ENTRA_CLIENT_SECRET" ]; then
        TOKEN_REQUEST="${TOKEN_REQUEST}&client_secret=$TA_ENTRA_CLIENT_SECRET"
    fi
    
    TOKEN_RESPONSE=$(curl -s -X POST \
      "https://login.microsoftonline.com/$TA_ENTRA_TENANT_ID/oauth2/v2.0/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "$TOKEN_REQUEST")
    
    ERROR=$(echo "$TOKEN_RESPONSE" | jq -r '.error // "none"')
    
    if [ "$ERROR" = "none" ]; then
        # Success!
        TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "    ✅ AUTHENTICATION SUCCESSFUL"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "Token (first 50 chars): ${TOKEN:0:50}..."
        echo ""
        
        # Decode token to show user info (without verification)
        echo "📋 Token Claims:"
        PAYLOAD=$(echo "$TOKEN" | cut -d. -f2)
        # Add padding if needed for base64
        PADDED=$(printf '%s' "$PAYLOAD" | sed 's/-/+/g; s/_/\//g')
        case $((${#PADDED} % 4)) in
            2) PADDED="${PADDED}==" ;;
            3) PADDED="${PADDED}=" ;;
        esac
        echo "$PADDED" | base64 -d 2>/dev/null | jq -r '
          "  User: \(.preferred_username // .upn // .email // .sub)",
          "  Name: \(.name // "N/A")",
          "  Roles: \(.roles // [] | join(", ") // "N/A")",
          "  Groups: \(.groups // [] | length) groups"
        '
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "💾 Export this to use in tests:"
        echo "export ENTRA_TOKEN=\"$TOKEN\""
        echo ""
        echo "🧪 Test with your agent:"
        echo "curl -X POST http://localhost:8000/integration-test-agent/1.0 \\"
        echo "  -H \"Authorization: Bearer \$ENTRA_TOKEN\" \\"
        echo "  -H \"Content-Type: application/json\" \\"
        echo "  -H \"X-API-Key: test-api-key-12345\" \\"
        echo "  -d '{\"items\": [{\"content_type\": \"text\", \"content\": \"What tools do you have?\"}]}' | jq"
        echo ""
        
        exit 0
    elif [ "$ERROR" = "authorization_pending" ]; then
        # Still waiting
        continue
    elif [ "$ERROR" = "slow_down" ]; then
        # Need to wait longer
        echo "⏸️  Slowing down polling..."
        sleep $INTERVAL
        continue
    else
        # Error occurred
        echo ""
        echo "❌ Authentication failed or timed out"
        echo "Error: $ERROR"
        echo "Description: $(echo "$TOKEN_RESPONSE" | jq -r '.error_description // "Unknown error"')"
        exit 1
    fi
done

echo ""
echo "❌ Authentication timed out"
echo "Please try again and complete the authentication faster."
exit 1

