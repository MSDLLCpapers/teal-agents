from abc import ABC, abstractmethod

from model.responses import VerifyTicketResponse


class TicketManager(ABC):
    @abstractmethod
    def create_ticket(self, orchestrator_name: str, user_id: str, ip_address: str) -> str:
        pass

    @abstractmethod
    def verify_ticket(
        self, orchestrator_name: str, ticket: str, ip_address: str
    ) -> VerifyTicketResponse:
        pass
