from pydantic import BaseModel

from auth.authenticator import Authenticator, AuthResponse


class UserIdOnlyAuthRequest(BaseModel):
    user_id: str


class UserIdOnlyAuthenticator(Authenticator[UserIdOnlyAuthRequest]):
    def authenticate(self, orchestrator_name: str, request: UserIdOnlyAuthRequest) -> AuthResponse:
        return AuthResponse(success=True, orch_name=orchestrator_name, user_id=request.user_id)
