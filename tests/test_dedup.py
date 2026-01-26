from luxnews.utils import unique_preserve_order


def test_unique_preserve_order():
    items = ["a", "b", "a", "c", "b"]
    assert unique_preserve_order(items) == ["a", "b", "c"]
