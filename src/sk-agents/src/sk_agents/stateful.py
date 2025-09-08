import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import UUID4, BaseModel, Field, validator
from redis.asyncio import Redis


class TaskStatus(Enum):
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"


class MultiModalItem(BaseModel):
    content_type: str
    content: str


class UserMessage(BaseModel):
    """
    New input model for the tealagents/v1alpha1 API version.
    Unlike BaseMultiModalInput, chat history is maintained server-side.
    """
    session_id: UUID4 | None = None
    task_id: UUID4 | None = None
    items: list[MultiModalItem]

    @validator('session_id', 'task_id', pre=True)
    def validate_uuid(cls, v):
        if v is not None and not isinstance(v, uuid.UUID):
            try:
                return uuid.UUID(v)
            except (ValueError, AttributeError) as err:
                raise ValueError(f"Invalid UUID format: {v}") from err
        return v


class TaskState(BaseModel):
    """Model for the state associated with a Task ID"""
    task_id: UUID4
    session_id: UUID4
    user_id: str  # User identity for authorization
    messages: list[dict[str, Any]]  # Chat history and execution trace
    status: TaskStatus = TaskStatus.RUNNING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RequestState(BaseModel):
    """Model for the state associated with a Request ID"""
    request_id: UUID4
    task_id: UUID4
    status: TaskStatus = TaskStatus.RUNNING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateResponse(BaseModel):
    """Response model including state identifiers"""
    session_id: UUID4
    task_id: UUID4
    request_id: UUID4
    status: TaskStatus
    content: Any


class StateManager(ABC):
    """Abstract base class for state management"""

    @abstractmethod
    async def create_task(self, session_id: UUID4 | None, user_id: str) -> tuple[UUID4, UUID4]:
        """Create a new task and return session_id and task_id"""

    @abstractmethod
    async def get_task(self, task_id: UUID4) -> TaskState:
        """Get a task by ID"""

    @abstractmethod
    async def update_task(self, task_state: TaskState) -> None:
        """Update a task state"""

    @abstractmethod
    async def create_request(self, task_id: UUID4) -> UUID4:
        """Create a new request and return request_id"""

    @abstractmethod
    async def get_request(self, request_id: UUID4) -> RequestState:
        """Get a request by ID"""

    @abstractmethod
    async def update_request(self, request_state: RequestState) -> None:
        """Update a request state"""

class InMemoryStateManager(StateManager):
    """In-memory implementation of state manager"""

    def __init__(self):
        self.tasks: dict[UUID4, TaskState] = {}
        self.requests: dict[UUID4, RequestState] = {}

    async def create_task(self, session_id: UUID4 | None, user_id: str) -> tuple[UUID4, UUID4]:
        session_id = session_id or uuid.uuid4()
        task_id = uuid.uuid4()
        self.tasks[task_id] = TaskState(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            messages=[]
        )
        return session_id, task_id

    async def get_task(self, task_id: UUID4) -> TaskState:
        if task_id not in self.tasks:
            raise ValueError(f"Task not found: {task_id}")
        return self.tasks[task_id]

    async def update_task(self, task_state: TaskState) -> None:
        task_state.updated_at = datetime.utcnow()
        self.tasks[task_state.task_id] = task_state

    async def create_request(self, task_id: UUID4) -> UUID4:
        request_id = uuid.uuid4()
        self.requests[request_id] = RequestState(
            request_id=request_id,
            task_id=task_id
        )
        return request_id

    async def get_request(self, request_id: UUID4) -> RequestState:
        if request_id not in self.requests:
            raise ValueError(f"Request not found: {request_id}")
        return self.requests[request_id]

    async def update_request(self, request_state: RequestState) -> None:
        request_state.updated_at = datetime.utcnow()
        self.requests[request_state.request_id] = request_state

class RedisStateManager(StateManager):
    """Redis implementation of state manager"""

    def __init__(self, redis_client: Redis, ttl: int | None = None):
        self.redis = redis_client
        self.ttl = ttl  # Time-to-live in seconds

    async def create_task(self, session_id: UUID4 | None, user_id: str) -> tuple[UUID4, UUID4]:
        session_id = session_id or uuid.uuid4()
        task_id = uuid.uuid4()
        task_state = TaskState(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            messages=[]
        )
        await self._set_task(task_state)
        return session_id, task_id

    async def get_task(self, task_id: UUID4) -> TaskState:
        key = f"task:{task_id}"
        data = await self.redis.get(key)
        if not data:
            raise ValueError(f"Task not found: {task_id}")
        return TaskState.parse_raw(data)

    async def update_task(self, task_state: TaskState) -> None:
        task_state.updated_at = datetime.utcnow()
        await self._set_task(task_state)

    async def _set_task(self, task_state: TaskState) -> None:
        key = f"task:{task_state.task_id}"
        await self.redis.set(key, task_state.json(), ex=self.ttl)

    async def create_request(self, task_id: UUID4) -> UUID4:
        request_id = uuid.uuid4()
        request_state = RequestState(
            request_id=request_id,
            task_id=task_id
        )
        await self._set_request(request_state)
        return request_id

    async def get_request(self, request_id: UUID4) -> RequestState:
        key = f"request:{request_id}"
        data = await self.redis.get(key)
        if not data:
            raise ValueError(f"Request not found: {request_id}")
        return RequestState.parse_raw(data)

    async def update_request(self, request_state: RequestState) -> None:
        request_state.updated_at = datetime.utcnow()
        await self._set_request(request_state)

    async def _set_request(self, request_state: RequestState) -> None:
        key = f"request:{request_state.request_id}"
        await self.redis.set(key, request_state.json(), ex=self.ttl)


class AuthenticationManager(ABC):
    """Abstract base class for authentication management"""

    @abstractmethod
    async def authenticate(self, token: str) -> str:
        """Authenticate a token and return the user ID"""
        pass

    @abstractmethod
    async def validate_task_access(self, task_id: UUID4, user_id: str) -> bool:
        """Validate if a user has access to a task"""
        pass


class MockAuthenticationManager(AuthenticationManager):
    """Mock implementation of authentication manager for development"""

    async def authenticate(self, token: str) -> str:
        # In mock implementation, just return the token as the user ID
        # In real implementation, this would validate the token with Entra ID
        return token or "anonymous-user"

    async def validate_task_access(self, task_id: UUID4, user_id: str) -> bool:
        # In mock implementation, always return True
        # In real implementation, this would check if the user owns the task
        return True
