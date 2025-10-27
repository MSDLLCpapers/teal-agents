from sk_agents.authorization.request_authorizer import RequestAuthorizer


class DummyAuthorizer(RequestAuthorizer):
    """
    Dummy authorizer for testing and development.
    
    Extracts user ID from Bearer token WITHOUT validation.
    Format: "Bearer <user_id>"
    
    WARNING: DO NOT USE IN PRODUCTION - provides NO security!
    Use EntraAuthorizer for production deployments.
    """
    async def authorize_request(self, auth_header: str) -> str:
        if not auth_header:
            return "dummyuser"
        
        # Extract user from Bearer token
        # Format: "Bearer alice@test.com" -> "alice@test.com"
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            user_id = parts[1].strip()
            if user_id:
                return user_id
        
        # Fallback for invalid format
        return "dummyuser"
