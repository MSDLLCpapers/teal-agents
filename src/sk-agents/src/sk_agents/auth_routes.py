"""
Authentication and OAuth-related routes for Teal Agents.

Includes custom OAuth verifier endpoint for Arcade authorization flows.
"""

import logging
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from arcadepy import AsyncArcade

logger = logging.getLogger(__name__)


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
            # Get user_id from the request
            # In production, extract from session cookie or JWT in authorization header
            authorization = request.headers.get("authorization")
            
            if not authorization:
                raise HTTPException(
                    status_code=401,
                    detail="Authorization required to verify OAuth flow"
                )
            
            # Extract user_id using the configured authorizer
            # Import here to avoid circular dependency
            from sk_agents.authorization.authorizer_factory import AuthorizerFactory
            from ska_utils import AppConfig
            
            app_config = AppConfig()
            authorizer_factory = AuthorizerFactory(app_config)
            authorizer = authorizer_factory.get_authorizer()
            
            user_id = await authorizer.authorize_request(authorization)
            
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Could not identify user from authorization"
                )
            
            logger.info(f"Verifying Arcade OAuth flow {flow_id} for user: {user_id}")
            
            # Confirm user identity with Arcade
            arcade_client = AsyncArcade()  # Uses ARCADE_API_KEY from environment
            
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

