from sk_agents.extra_data_collector import (
    ExtraData,
    ExtraDataCollector,
    ExtraDataElement,
    ExtraDataPartial,
)


def test_new_from_json_valid():
    json_input = '{"extra_data": {"items": [{"key": "foo", "value": "bar"}]}}'
    result = ExtraDataPartial.new_from_json(json_input)

    assert result.extra_data is not None
    assert len(result.extra_data.items) == 1
    assert result.extra_data.items[0].key == "foo"
    assert result.extra_data.items[0].value == "bar"


def test_new_from_json_null_extra_data():
    json_input = '{"extra_data": null}'
    result = ExtraDataPartial.new_from_json(json_input)

    assert result.extra_data is None


def test_new_from_json_empty_items():
    json_input = '{"extra_data": {"items": []}}'
    result = ExtraDataPartial.new_from_json(json_input)

    assert result.extra_data is not None
    assert result.extra_data.items == []


def test_new_from_json_missing_extra_data():
    json_input = "{}"  # 'extra_data' key missing
    result = ExtraDataPartial.new_from_json(json_input)

    assert result.extra_data is None


def test_add_extra_data_adds_item():
    collector = ExtraDataCollector()
    collector.add_extra_data("key1", "value1")

    assert collector.num_items() == 1
    assert not collector.is_empty()

    extra_data = collector.get_extra_data()
    assert extra_data is not None
    assert isinstance(extra_data.items[0], ExtraDataElement)
    assert extra_data.items[0].key == "key1"
    assert extra_data.items[0].value == "value1"


def test_add_extra_data_multiple_items():
    collector = ExtraDataCollector()
    collector.add_extra_data("k1", "v1")
    collector.add_extra_data("k2", "v2")
    collector.add_extra_data("k3", "v3")

    assert collector.num_items() == 3
    items = collector.get_extra_data().items
    keys = [item.key for item in items]
    values = [item.value for item in items]

    assert keys == ["k1", "k2", "k3"]
    assert values == ["v1", "v2", "v3"]


def test_add_extra_data_allows_duplicate_keys():
    collector = ExtraDataCollector()
    collector.add_extra_data("dup", "v1")
    collector.add_extra_data("dup", "v2")

    assert collector.num_items() == 2
    items = collector.get_extra_data().items
    assert items[0].key == "dup"
    assert items[1].key == "dup"
    assert items[0].value == "v1"
    assert items[1].value == "v2"


def test_add_extra_data_items_adds_all_elements():
    collector = ExtraDataCollector()
    elements = [
        ExtraDataElement(key="a", value="1"),
        ExtraDataElement(key="b", value="2"),
        ExtraDataElement(key="c", value="3"),
    ]
    extra_data = ExtraData(items=elements)

    collector.add_extra_data_items(extra_data)

    assert collector.num_items() == 3
    data_items = collector.get_extra_data().items
    assert [(item.key, item.value) for item in data_items] == [("a", "1"), ("b", "2"), ("c", "3")]


def test_add_extra_data_items_empty_list():
    collector = ExtraDataCollector()
    extra_data = ExtraData(items=[])
    collector.add_extra_data_items(extra_data)

    assert collector.num_items() == 0
    assert collector.is_empty()


def test_add_extra_data_items_none_input():
    collector = ExtraDataCollector()
    collector.add_extra_data_items(None)  # Should be safely ignored, no exception

    assert collector.num_items() == 0
    assert collector.get_extra_data() is None


def test_add_extra_data_items_mixed_adds():
    collector = ExtraDataCollector()
    collector.add_extra_data("initial", "val")

    new_items = ExtraData(
        items=[ExtraDataElement(key="x", value="10"), ExtraDataElement(key="y", value="20")]
    )

    collector.add_extra_data_items(new_items)

    assert collector.num_items() == 3
    keys = [item.key for item in collector.get_extra_data().items]
    assert keys == ["initial", "x", "y"]
