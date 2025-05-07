from semantic_kernel.kernel_pydantic import KernelBaseModel
from ska_utils import ModuleLoader

from sk_agents.ska_types import (
    BaseEmbeddedImage,
    BaseInput,
    BaseInputWithUserContext,
    BaseMultiModalInput,
)


class TypeLoader:
    base_types: dict[str, type[KernelBaseModel]]

    def __init__(self, types_module: str | None = None):
        self.base_types = {}
        self.types_module = None
        self.custom_module = None

        self.set_types_module(types_module)

    @staticmethod
    def _parse_module_name(types_module: str) -> str:
        return types_module.split("/")[-1].split(".")[0]

    def set_types_module(self, types_module: str | None):
        self.types_module = types_module
        if self.types_module:
            self.custom_module = ModuleLoader.load_module(types_module)
        else:
            self.custom_module = None

    @staticmethod
    def _get_standard_type(type: str) -> type[KernelBaseModel] | None:
        match type:
            case "BaseInput":
                return BaseInput
            case "BaseInputWithUserContext":
                return BaseInputWithUserContext
            case "BaseMultiModalInput":
                return BaseMultiModalInput
            case "BaseEmbeddedImage":
                return BaseEmbeddedImage
            case _:
                return None

    def get_type(self, type_name: str) -> type[KernelBaseModel] | None:
        standard_type = TypeLoader._get_standard_type(type_name)
        if standard_type:
            return standard_type

        if not self.custom_module:
            return None

        if type_name in self.base_types:
            return self.base_types[type_name]

        if hasattr(self.custom_module, type_name):
            return_type = getattr(self.custom_module, type_name)
            self.base_types[type_name] = return_type
            return return_type
        else:
            raise ValueError(f"Output type {type_name} not found")


_type_loader: TypeLoader | None = None


def get_type_loader(types_module: str | None = None) -> TypeLoader:
    global _type_loader
    if not _type_loader:
        _type_loader = TypeLoader(types_module)
    return _type_loader
