from pydantic import BaseModel

from auth.authenticator import Authenticator, AuthResponse


class ExampleUserIdOnlyAuthRequest(BaseModel):
    user_id: str


class ExampleUserIdOnlyAuthenticator(Authenticator[ExampleUserIdOnlyAuthRequest]):
    def authenticate(
        self, orchestrator_name: str, request: ExampleUserIdOnlyAuthRequest
    ) -> AuthResponse:
        if request.user_id == "good_id":
            return AuthResponse(success=True, orch_name=orchestrator_name, user_id=request.user_id)
        else:
            return AuthResponse(success=False, orch_name=orchestrator_name, user_id=request.user_id)
