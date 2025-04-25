from ska_utils import AppConfig

from configs import (
    TA_SERVICES_ENDPOINT,
    TA_SERVICES_TOKEN,
    TA_SERVICES_TYPE,
)
from services.external_services_client import ExternalServicesClient
from services.internal_services_client import InternalServicesClient
from services.services_client import ServicesClient


def new_client(orchestrator_name: str) -> ServicesClient:
    app_config = AppConfig()
    client_type = app_config.get(TA_SERVICES_TYPE.env_name)
    match client_type:
        case "external":
            return _new_client_external(orchestrator_name)
        case _:
            return _new_client_internal()


def _new_client_internal() -> InternalServicesClient:
    return InternalServicesClient()


def _new_client_external(orchestrator_name: str) -> ExternalServicesClient:
    app_config = AppConfig()

    endpoint = app_config.get(TA_SERVICES_ENDPOINT.env_name)
    if not endpoint:
        raise ValueError("No endpoint found for external services client")
    token = app_config.get(TA_SERVICES_TOKEN.env_name)

    return ExternalServicesClient(
        orchestrator_name=orchestrator_name, endpoint=endpoint, token=token
    )
