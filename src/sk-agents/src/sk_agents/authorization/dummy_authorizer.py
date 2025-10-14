from sk_agents.authorization.request_authorizer import RequestAuthorizer


class DummyAuthorizer(RequestAuthorizer):
    async def authorize_request(self, auth_header: str) -> str:
        return "dummyuser"
