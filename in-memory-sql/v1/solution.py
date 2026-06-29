from typing import Callable, List, Optional

ValueType = str | int

# Each operator maps the sign of a comparison (-1, 0, 1) to a boolean.
OPS: dict[str, Callable[[int], bool]] = {
    "=": lambda sign: sign == 0,
    ">": lambda sign: sign > 0,
    "<": lambda sign: sign < 0,
}


class Table:
    def __init__(self, name: str, columnNames: List[str]) -> None:
        self.name = name
        self.colNameToIndex: dict[str, int] = {
            col: pos for pos, col in enumerate(columnNames)
        }
        self.rows: List[List[ValueType]] = []

    @staticmethod
    def _parse(value: str) -> ValueType:
        """Infer the type of a raw string: an int when it parses, else a string."""
        try:
            return int(value)
        except ValueError:
            return value

    @staticmethod
    def _compare(stored: ValueType, raw: str) -> Optional[int]:
        """Return the sign of (stored <=> raw), or None if the types are incompatible.

        Comparing an int-typed cell against a non-numeric value (or vice versa) is
        treated as "no match" rather than an error.
        """
        other = Table._parse(raw)
        if type(other) is not type(stored):
            return None
        return (stored > other) - (stored < other)

    @staticmethod
    def _sortKey(value: ValueType) -> tuple[int, ValueType]:
        """Build a sort key that never compares ints against strings.

        Within an orderBy column different rows may hold different inferred types;
        prefix the key with a type rank so ordering is total and never raises.
        """
        return (0, value) if isinstance(value, int) else (1, value)

    def insert(self, values: List[str]) -> int:
        if len(values) != len(self.colNameToIndex):
            raise ValueError(
                f"Expected {len(self.colNameToIndex)} values, got {len(values)}"
            )
        rowId = len(self.rows)
        self.rows.append([self._parse(value) for value in values])
        return rowId

    def _colIndex(self, col: str) -> int:
        if col not in self.colNameToIndex:
            raise ValueError(f"Unknown column {col!r} in table {self.name!r}")
        return self.colNameToIndex[col]

    def select(
        self, conditions: List[List[str]], orderBy: List[str]
    ) -> List[int]:
        matches = list(range(len(self.rows)))

        for condition in conditions:
            col, op, value = condition
            if op not in OPS:
                raise ValueError(f"Invalid operator {op!r}")
            colIndex = self._colIndex(col)
            matches = [
                rowId
                for rowId in matches
                if (sign := self._compare(self.rows[rowId][colIndex], value))
                is not None
                and OPS[op](sign)
            ]

        if orderBy:
            colPositions = [self._colIndex(col) for col in orderBy]
            matches.sort(
                key=lambda rowId: [
                    self._sortKey(self.rows[rowId][pos]) for pos in colPositions
                ]
            )

        return matches


class SQLManager:
    def __init__(self) -> None:
        self.tables: dict[str, Table] = {}

    def createTable(self, tableName: str, columnNames: List[str]) -> Table:
        if tableName in self.tables:
            raise ValueError(f"Table {tableName!r} already exists")
        table = Table(tableName, columnNames)
        self.tables[tableName] = table
        return table

    def _table(self, tableName: str) -> Table:
        if tableName not in self.tables:
            raise ValueError(f"Table {tableName!r} does not exist")
        return self.tables[tableName]

    def insert(self, tableName: str, values: List[str]) -> None:
        self._table(tableName).insert(values)

    def select(
        self, tableName: str, conditions: List[List[str]], orderBy: List[str]
    ) -> List[int]:
        return self._table(tableName).select(conditions, orderBy)
import unittest


class TestSQLManager(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SQLManager()
        self.db.createTable("users", ["name", "age"])
        self.db.insert("users", ["Alice", "30"])
        self.db.insert("users", ["Bob", "25"])
        self.db.insert("users", ["Charlie", "35"])
        self.db.insert("users", ["Mary", "25"])

    def test_problem_example(self):
        self.assertEqual(self.db.select("users", [["age", ">", "28"]], []), [0, 2])
        self.assertEqual(
            self.db.select("users", [["age", ">", "25"], ["name", "<", "C"]], []),
            [0],
        )
        self.assertEqual(
            self.db.select("users", [["age", ">", "20"]], ["name"]), [0, 1, 2, 3]
        )
        self.assertEqual(
            self.db.select("users", [["age", ">", "24"]], ["age", "name"]),
            [1, 3, 0, 2],
        )

    def test_no_conditions_no_order_returns_insertion_order(self):
        self.assertEqual(self.db.select("users", [], []), [0, 1, 2, 3])

    def test_no_match(self):
        self.assertEqual(self.db.select("users", [["age", "=", "22"]], []), [])

    def test_equality_operator(self):
        self.assertEqual(self.db.select("users", [["age", "=", "25"]], []), [1, 3])

    def test_string_comparison(self):
        # Lexicographic comparison on a string column.
        self.assertEqual(self.db.select("users", [["name", "=", "Bob"]], []), [1])
        self.assertEqual(
            self.db.select("users", [["name", ">", "Charlie"]], []), [3]
        )

    def test_multi_column_order_tiebreak(self):
        # Sorted by age asc, then name asc.
        self.assertEqual(
            self.db.select("users", [], ["age", "name"]), [1, 3, 0, 2]
        )

    def test_descending_not_supported_uses_ascending(self):
        self.assertEqual(self.db.select("users", [], ["name"]), [0, 1, 2, 3])

    def test_type_mismatch_filters_out(self):
        # An int-typed column compared against a non-numeric value matches nothing.
        self.assertEqual(self.db.select("users", [["age", "=", "old"]], []), [])
        self.assertEqual(self.db.select("users", [["age", ">", "old"]], []), [])

    def test_mixed_type_column_sorts_without_error(self):
        db = SQLManager()
        db.createTable("t", ["v"])
        db.insert("t", ["10"])      # int
        db.insert("t", ["apple"])   # str
        db.insert("t", ["2"])       # int
        db.insert("t", ["banana"])  # str
        # Ints sort before strings; ints numerically, strings lexicographically.
        self.assertEqual(db.select("t", [], ["v"]), [2, 0, 1, 3])

    def test_duplicate_table_raises(self):
        db = SQLManager()
        db.createTable("t", ["a"])
        with self.assertRaises(ValueError):
            db.createTable("t", ["a"])

    def test_missing_table_raises(self):
        db = SQLManager()
        with self.assertRaises(ValueError):
            db.select("ghost", [], [])
        with self.assertRaises(ValueError):
            db.insert("ghost", ["x"])

    def test_invalid_column_raises(self):
        with self.assertRaises(ValueError):
            self.db.select("users", [["height", ">", "1"]], [])
        with self.assertRaises(ValueError):
            self.db.select("users", [], ["height"])

    def test_invalid_operator_raises(self):
        with self.assertRaises(ValueError):
            self.db.select("users", [["age", "!=", "25"]], [])

    def test_wrong_value_count_raises(self):
        db = SQLManager()
        db.createTable("t", ["a", "b"])
        with self.assertRaises(ValueError):
            db.insert("t", ["only-one"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
