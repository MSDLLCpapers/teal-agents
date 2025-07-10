from abc import ABC, abstractmethod

class RequestAuthorizer(ABC):
    @abstractmethod
    def authorize_request(self, auth_header: str) -> str:
        """
        Validates the given authorization header and returns a unique identifier
        for the authenticated user.

        Parameters:
            auth_header (str): The value of the 'Authorization' HTTP header.
                Typically, this is in the format 'Bearer <token>' or some other
                scheme depending on the implementation.

        Returns:
            str: A unique string that identifies the authenticated user.
                This could be a user ID, username, email, or any other unique
                identifier suitable for tracking and authorization.
            Examples:
                "user_12345"
                "alice@example.com"

        Raises:
            ValueError: If the authorization header is missing, malformed, or invalid.
            AuthenticationError (optional): If used in your implementation, it may
                be raised to signal an authentication failure.
        """
        pass
