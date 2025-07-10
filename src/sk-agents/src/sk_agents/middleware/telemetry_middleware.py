from contextlib import nullcontext

from fastapi import FastAPI, Request, Response
from opentelemetry.propagate import extract
from ska_utils import Telemetry
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from typing import List


class TelemetryMiddleware(BaseHTTPMiddleware):
    _telemetry_excluded_path_suffixes: List[str] = ["/openapi.json"]

    def __init__(self, app: FastAPI, st: Telemetry):
        super().__init__(app)
        self.st = st

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        context = extract(request.headers)
        with (
            self.st.tracer.start_as_current_span(
                f"{request.method} {request.url.path}", context=context
            )
            if self.st.telemetry_enabled()
            and not any(
                request.url.path.endswith(suffix)
                for suffix in self._telemetry_excluded_path_suffixes
            )
            else nullcontext()
        ):
            response = await call_next(request)
        return response
