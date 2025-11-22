from dapr.ext.workflow import WorkflowActivityContext, WorkflowContext
from pydantic import BaseModel

class MyInput(BaseModel):
    name: str

class MyWorkflow:
    def __init__(self, ctx: WorkflowContext, input: MyInput):
        self.ctx = ctx
        self.input = input

    def run(self):
        yield self.ctx.call_activity(hello_world, input=self.input)

def hello_world(ctx: WorkflowActivityContext, input: MyInput):
    print(f"Hello {input.name}!")
    return f"Hello {input.name}!"
