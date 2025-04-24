import json

from pydantic import BaseModel


class ExtraDataElement(BaseModel):
    key: str
    value: str


class ExtraData(BaseModel):
    items: list[ExtraDataElement]


class ExtraDataPartial(BaseModel):
    extra_data: ExtraData | None = None

    @staticmethod
    def new_from_json(json_str: str) -> "ExtraDataPartial":
        return ExtraDataPartial(**json.loads(json_str))


class ExtraDataCollector:
    def __init__(self):
        self._extra_data_items: list[ExtraDataElement] = []

    def add_extra_data(self, key: str, value: str):
        self._extra_data_items.append(ExtraDataElement(key=key, value=value))

    def add_extra_data_items(self, extra_data: ExtraData):
        if extra_data and extra_data.items:
            for item in extra_data.items:
                self.add_extra_data(item.key, item.value)

    def num_items(self) -> int:
        return len(self._extra_data_items)

    def is_empty(self) -> bool:
        return self.num_items() == 0

    def get_extra_data(self) -> ExtraData | None:
        if not self._extra_data_items:
            return None
        return ExtraData(items=self._extra_data_items)
