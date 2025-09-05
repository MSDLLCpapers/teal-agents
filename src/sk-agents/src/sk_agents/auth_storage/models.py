from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BaseAuthData(BaseModel):
    auth_type: str


class OAuth2AuthData(BaseAuthData):
    auth_type: Literal["oauth2"] = "oauth2"
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime
    # The scopes this token is valid for.
    scopes: list[str] = []


# A union of all supported auth data types.
# Right now only OAuth2 is supported, but when more are added
# the below will need to be updated to a discriminated union.
#
# For example:
# AuthData = Union[OAuth2AuthData, AnotherAuthData]
AuthData = OAuth2AuthData
