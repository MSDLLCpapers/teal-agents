1. New Logic Path
- New folders at src/sk_agents/tealagents and src/sk_agents/tealagents/v1alpha1
- New __init__.py files in each to handle invocation logic
- New BaseHandler subclass in called agent in src/sk_agents/tealagents/v1alpha1/agent
- Create new AppV3 similar to AppV2
- Should extract/determine correct info and add routes from routes.py
- Extend routes to route to new handlers based on `tealagents` as first token of config value

2. Create new abstract class RequestAuthorizer
- abstract method authorize_request(auth_header: str) -> str
    - Should return authorized unique user identifier

3. Create dummy implementation of RequestAuthorizer
- Always returns 'dummyuser'

4. Create authorizer factory
- Two new environment variables, authorizer module and authorizer name
- Based on those, instantiate appropriate authorizer and return

5. New input message type: UserMessage
   class UserMessage(BaseModel):
   session_id: str | None = None
   task_id: str | None = None
   items: list[MultiModalItem]

6. Create model for task persistence
   class AgentTaskItem(BaseModel):
   task_id: str
   role: literal "user" or "assistant"
   item: MultiModalItem
   request_id: str
   updated: datetime

class AgentTask(BaseModel):
task_id: str
session_id: str
items: list[AgentTaskItem]

7. Create abstract class TaskPersistenceManager
- create, load, update, delete

8. Create in-memory implementation of TaskPersistenceManager

9. Create persistence manager factory
- Two new environment variables, persistence manager module and persistence manager class
- Based on those, instantiate appropriate persistence manager and return


10. Handling new config type tealagents/v1alpha1
- Handler will need to implement both invoke and invoke_stream
- All requests must be authorized - Retrieve authorizer from factory and authorize request
- retrieve configured persistence manager
- If no session_id is provided, generate session_id
- Generate request_id
- If task_id is provided
    - retrieve task from persistence
    - verify current user is owner of persisted task
    - save new message to existing task as new task item
- If task_id is not provided
    - generate new task_id
    - create new task
    - add new message to task
    - save task
- Build chat history appropriately, and invoke or invoke_stream
- Create new InvokeResponse and PartialResponse analogs that include session_id, task_id, and request_id in those response
- In new InvokeResponse, you can collapse output fields to just `output` which contains the text response
- Once final response is received, add new item to task and persist