from sk_agents.authorization.request_authorizer import RequestAuthorizer


class DummyAuthorizer(RequestAuthorizer):
    async def authorize_request(self, auth_header: str) -> str:
        return "dummyuser"

    async def validate_platform_auth(self, auth_token: str) -> str:
        return auth_token

    async def refresh_access_token(self, refresh_token) -> str:
        return refresh_token