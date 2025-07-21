from .request_authorizer import RequestAuthorizer


class DummyAuthorizer(RequestAuthorizer):
    def authorize_request(self, auth_header: str) -> str:
        return "dummyuser"
