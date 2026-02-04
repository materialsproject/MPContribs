from mpcontribs.client import Table


def test_table():

    data = {
        "first_name": ["Todd", "Willie", "Mike"],
        "family_name": ["Bonzalez", "Dustice", "Truk"],
        "age": [31, 24, 28],
        "batting_average": [0.777, 0.5, 0.81],
    }
    test_table = Table(data)

    # Calling `as_dict` transforms the data in a `Table`
    table_as_dict = Table(test_table.copy()).as_dict()
    assert all(
        table_as_dict.get(k) for k in ("attrs", "columns", "data", "index", "name")
    )
    table_info = test_table.info()
    assert {y.strip() for y in table_info["columns"].split(",")} == set(
        test_table.columns
    )
    assert table_info["nrows"] == len(test_table)

    table_roundtrip = Table.from_dict(table_as_dict)

    # `tolist()` needed to compare base python types
    for t in (test_table, table_roundtrip):
        assert all(
            isinstance(v, str)
            for col in ("family_name", "first_name")
            for v in t[col].tolist()
        )
        assert all(isinstance(v, int) for v in t.age.tolist())
        assert all(isinstance(v, float) for v in t.batting_average.tolist())
