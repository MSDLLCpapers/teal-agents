from typing import (
    Any,
    Union,
    List,
    Callable,
    get_type_hints,
    get_origin,
    get_args,
    Generic,
)

from ska_utils import ModuleLoader
from dapr.ext.workflow import WorkflowActivityContext


class WorkflowLoader:
    def __init__(self, workflow_module: str | None = None):
        self.workflow_module = None
        self.custom_module = None

        self.set_workflow_module(workflow_module)

    @staticmethod
    def _parse_module_name(module_file: str) -> str:
        return module_file.split("/")[-1].split(".")[0]

    def set_workflow_module(self, workflow_module: Union[str, None]):
        self.workflow_module = workflow_module
        if self.workflow_module:
            self.custom_module = ModuleLoader.load_module(workflow_module)
        else:
            self.custom_module = None

    def get_workflow_object(self, object_name: str) -> Any:
        if hasattr(self.custom_module, object_name):
            return getattr(self.custom_module, object_name)
        else:
            raise ValueError(f"Workflow object {object_name} not found")

    def find_activity_function(self) -> List[Callable]:
        return self._find_functions_with_param_type(WorkflowActivityContext)

    def _find_functions_with_param_type(self, param_type: type) -> List[Callable]:
        """
        Finds functions in the custom module whose first parameter has a specific type.

        Args:
            param_type: The type of the first parameter to search for.

        Returns:
            A list of callable objects (functions or methods) that match the criteria.
        """

        matching_functions = []
        if self.custom_module is None:
            return matching_functions

        for name, obj in self.custom_module.__dict__.items():
            if callable(obj):  # Check if it's callable (function or method)
                try:
                    type_hints = get_type_hints(obj)
                    if type_hints:  # Check if there are type hints
                        first_param_type = type_hints.get(
                            next(iter(type_hints))
                        )  # Get the type of the first parameter. This assumes parameters are ordered, which is generally true.
                        if first_param_type:
                            # Handle generics (e.g., List[str], etc.):
                            origin = get_origin(first_param_type)
                            args = get_args(first_param_type)

                            if origin is not None:  # Check if the type is generic
                                if (
                                    origin is not Generic
                                    and issubclass(origin, param_type)
                                ):  # Check if the origin is not Generic and a subclass of the target type
                                    matching_functions.append(obj)
                                elif (
                                    origin is Generic
                                ):  # If it's a generic type, we need to check the first parameter
                                    if (
                                        len(args) > 0
                                        and isinstance(args[0], type)
                                        and issubclass(args[0], param_type)
                                    ):
                                        matching_functions.append(obj)
                            elif isinstance(first_param_type, type) and issubclass(
                                first_param_type, param_type
                            ):  # If it's not generic, do a simple subclass check
                                matching_functions.append(obj)

                except Exception as e:  # Handle potential errors (e.g., no type hints)
                    print(
                        f"Error inspecting {name}: {e}"
                    )  # It's better to log this rather than crash the program
                    pass  # Or you might want to raise the exception if you want to halt on type-hint related errors

        return matching_functions


_workflow_loader: WorkflowLoader | None = None


def get_workflow_loader(workflow_module: str | None = None) -> WorkflowLoader:
    global _workflow_loader
    if not _workflow_loader:
        _workflow_loader = WorkflowLoader(workflow_module)
    return _workflow_loader
