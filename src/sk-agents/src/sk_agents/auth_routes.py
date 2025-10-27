"""
Authentication and OAuth-related routes for Teal Agents.

Includes custom OAuth verifier endpoint for Arcade authorization flows.

PRODUCTION APPROACH:
- When Arcade returns authorization_required, it includes a flow_id in the auth_url
- We parse the flow_id from the auth_url and store flow_id -> user_id mapping
- When Arcade redirects browser to our verifier, we look up user_id by flow_id
- This works for multi-user production without sessions or cookies
"""

import logging
import re
from urllib.parse import parse_qs, urlparse
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from arcadepy import AsyncArcade
from typing import Dict

logger = logging.getLogger(__name__)

# Flow ID to User ID mapping
# TODO: For multi-instance deployments, use Redis instead of in-memory dict
_flow_user_mapping: Dict[str, str] = {}


def extract_flow_id_from_auth_url(auth_url: str) -> str | None:
    """
    Extract flow_id from Arcade's authorization URL.
    
    Arcade includes the flow_id in the 'state' parameter of the OAuth URL.
    
    Example:
        https://slack.com/oauth/v2/authorize?...&state=flow-id-here
    
    Returns:
        flow_id if found, None otherwise
    """
    try:
        # Clean URL - remove any markdown formatting or trailing characters
        auth_url = auth_url.strip().rstrip('),]')
        
        # CRITICAL: Decode Unicode escapes like \u0026 → &
        # Arcade returns JSON-encoded URLs with Unicode escapes
        auth_url = auth_url.encode().decode('unicode_escape')
        
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)
        flow_id = params.get('state', [None])[0]
        if flow_id:
            logger.info(f"Extracted flow_id from auth_url: {flow_id}")
            return flow_id
        else:
            logger.error(f"No 'state' parameter found in auth_url: {auth_url}")
            return None
    except Exception as e:
        logger.error(f"Exception extracting flow_id from auth_url: {e}, url={auth_url[:100]}")
        return None


def store_flow_user_mapping(flow_id: str, user_id: str):
    """
    Store flow_id -> user_id mapping for verifier lookup.
    
    Called when agent receives authorization_required response from Arcade.
    The flow_id is extracted from the auth_url and stored with the user_id.
    
    TODO: For production multi-instance:
    - Use Redis with TTL (flows expire after 15 minutes)
    - Key format: f"arcade:flow:{flow_id}"
    - Value: user_id
    - TTL: 900 seconds (15 minutes)
    """
    _flow_user_mapping[flow_id] = user_id
    logger.info(f"Stored flow mapping: {flow_id} -> {user_id}")


def get_user_from_flow(flow_id: str) -> str | None:
    """
    Retrieve user_id for a flow_id.
    
    Called by custom verifier when Arcade redirects after authorization.
    
    TODO: For production multi-instance:
    - Look up in Redis: redis.get(f"arcade:flow:{flow_id}")
    - Delete after retrieval (one-time use)
    """
    user_id = _flow_user_mapping.get(flow_id)
    if user_id:
        # Clean up mapping after use (one-time)
        del _flow_user_mapping[flow_id]
        logger.info(f"Retrieved and removed flow mapping: {flow_id} -> {user_id}")
    return user_id


def get_auth_routes() -> APIRouter:
    """
    Create router for authentication and OAuth-related endpoints.
    
    Returns:
        APIRouter with auth endpoints
    """
    router = APIRouter(prefix="/auth", tags=["Authentication"])
    
    @router.get("/arcade/verify")
    async def arcade_oauth_verifier(
        flow_id: str = Query(..., description="OAuth flow ID from Arcade"),
        request: Request = None
    ):
        """
        Custom OAuth verifier endpoint for Arcade authorization flows.
        
        This endpoint is called by Arcade after a user completes an OAuth
        authorization flow. It confirms the user's identity with Arcade
        and triggers re-discovery of MCP tools for the user.
        
        Configure this URL in Arcade Dashboard > Auth > Settings > Custom Verifier.
        
        Args:
            flow_id: The OAuth flow identifier from Arcade
            request: FastAPI request object
            
        Returns:
            Redirect to success page or error response
        """
        try:
            # PRODUCTION APPROACH: Look up user_id from flow mapping
            # The flow_id was stored when Arcade returned authorization_required
            user_id = get_user_from_flow(flow_id)
            
            if not user_id:
                logger.error(
                    f"No user mapping found for flow_id: {flow_id}. "
                    f"This means either:\n"
                    f"1. The authorization flow wasn't initiated through this server\n"
                    f"2. The flow expired (flows are deleted after first use)\n"
                    f"3. Server restarted and lost in-memory mappings (use Redis in production)"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown or expired authorization flow: {flow_id}"
                )
            
            logger.info(f"Verifying Arcade OAuth flow {flow_id} for user: {user_id}")
            
            # Confirm user identity with Arcade
            import os
            api_key = os.getenv("ARCADE_API_KEY")
            if not api_key:
                logger.error("ARCADE_API_KEY environment variable not set")
                raise HTTPException(status_code=500, detail="Server configuration error: ARCADE_API_KEY not set")
            
            arcade_client = AsyncArcade(api_key=api_key)
            
            result = await arcade_client.auth.confirm_user(
                flow_id=flow_id,
                user_id=user_id
            )
            
            logger.info(f"Arcade OAuth verification successful for user {user_id}, auth_id: {result.auth_id}")
            
            # Clear user's MCP discovery cache to trigger re-discovery with new authorizations
            # This ensures the user sees newly authorized tools on their next request
            try:
                # Get the handler instance to clear cache
                # Note: This assumes the handler is accessible via app state
                # If not available, re-discovery will happen naturally on next request
                if hasattr(request.app.state, 'teal_handler'):
                    handler = request.app.state.teal_handler
                    if hasattr(handler, 'clear_user_mcp_cache'):
                        handler.clear_user_mcp_cache(user_id)
                        logger.info(f"Cleared MCP cache for user {user_id} - will re-discover on next request")
                else:
                    logger.info(f"Handler not accessible, user {user_id} will re-discover on next request")
            except Exception as e:
                logger.warning(f"Could not clear MCP cache for user {user_id}: {e}")
                # Non-critical - discovery will eventually happen
            
            # Option 1: Redirect to Arcade's next_uri
            if hasattr(result, 'next_uri') and result.next_uri:
                return RedirectResponse(url=result.next_uri)
            
            # Option 2: Show success page
            return HTMLResponse(content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Authorization Successful</title>
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            margin: 0;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        }
                        .container {
                            background: white;
                            padding: 2rem;
                            border-radius: 1rem;
                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                            text-align: center;
                            max-width: 400px;
                        }
                        h1 { color: #333; margin-bottom: 1rem; }
                        p { color: #666; }
                        .success-icon { font-size: 4rem; color: #10b981; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="success-icon">✓</div>
                        <h1>Authorization Successful!</h1>
                        <p>You've successfully authorized the tool.</p>
                        <p>You can now close this window and return to your chat.</p>
                    </div>
                </body>
                </html>
            """, status_code=200)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OAuth verification failed for flow {flow_id}: {e}")
            return HTMLResponse(content=f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Authorization Failed</title>
                    <style>
                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            margin: 0;
                            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                        }}
                        .container {{
                            background: white;
                            padding: 2rem;
                            border-radius: 1rem;
                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                            text-align: center;
                            max-width: 400px;
                        }}
                        h1 {{ color: #333; margin-bottom: 1rem; }}
                        p {{ color: #666; }}
                        .error-icon {{ font-size: 4rem; color: #ef4444; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-icon">✕</div>
                        <h1>Authorization Failed</h1>
                        <p>Something went wrong during authorization.</p>
                        <p>Please try again or contact support.</p>
                    </div>
                </body>
                </html>
            """, status_code=400)
    
    return router

