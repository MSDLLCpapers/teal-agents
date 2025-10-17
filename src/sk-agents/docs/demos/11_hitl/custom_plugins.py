from semantic_kernel.functions.kernel_function_decorator import kernel_function
from sk_agents.ska_types import BasePlugin


class sensitive_plugin(BasePlugin):
    @kernel_function(description="invoke when a math problem is solved")
    def delete_user_data(self):
        return "you shouldnt see me"