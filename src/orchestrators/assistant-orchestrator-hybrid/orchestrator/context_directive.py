from enum import Enum

from pydantic import BaseModel

from jose_types import ExtraData
from model import ContextType


class ContextDirectiveOp(Enum):
    SET = "set-context"
    ADD = "add-context"
    UPDATE = "update-context"
    DELETE = "delete-context"


class ContextDirective(BaseModel):
    op: ContextDirectiveOp
    key: str
    value: str | None = None
    type: ContextType | None = None


def _parse_add_extra_data(value: str) -> tuple[str, str, ContextType]:
    (ed_key, ed_value, ed_type) = value.split(":", maxsplit=3)
    if not ed_key or not ed_value:
        raise ValueError("Key and value must be provided")

    ed_type_actual = (
        ContextType.PERSISTENT if ed_type == ContextType.PERSISTENT.value else ContextType.TRANSIENT
    )

    return ed_key, ed_value, ed_type_actual


def _parse_update_extra_data(value: str) -> tuple[str, str]:
    (ed_key, ed_value) = value.split(":", maxsplit=2)
    if not ed_key or not ed_value:
        raise ValueError("Key and value must be provided")

    return ed_key, ed_value


def parse_context_directives(extra_data: ExtraData) -> list[ContextDirective]:
    directives: list[ContextDirective] = []
    for item in extra_data.items:
        match item.key:
            case ContextDirectiveOp.SET.value:
                key, value = _parse_update_extra_data(item.value)
                directives.append(
                    ContextDirective(
                        op=ContextDirectiveOp.SET,
                        key=key,
                        value=value,
                        type=ContextType.TRANSIENT,
                    )
                )
            case ContextDirectiveOp.ADD.value:
                key, value, item_type = _parse_add_extra_data(item.value)
                directives.append(
                    ContextDirective(
                        op=ContextDirectiveOp.ADD,
                        key=key,
                        value=value,
                        type=item_type,
                    )
                )
            case ContextDirectiveOp.UPDATE.value:
                key, value = _parse_update_extra_data(item.value)
                directives.append(
                    ContextDirective(op=ContextDirectiveOp.UPDATE, key=key, value=value, type=None)
                )
            case ContextDirectiveOp.DELETE.value:
                directives.append(
                    ContextDirective(
                        op=ContextDirectiveOp.DELETE,
                        key=item.value,
                        value=None,
                        type=None,
                    )
                )
            case _:
                continue
    return directives
