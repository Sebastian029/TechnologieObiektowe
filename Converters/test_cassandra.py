import unittest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime
import uuid
import json
from cassandra.cluster import Cluster, Session
from cassandra.query import dict_factory

# Import class to test
from cassandra_converter import PyCassandraConverter


class TestPyCassandraConverter(unittest.TestCase):
    def setUp(self):
        """Prepare tests - mock dependencies."""
        # Mock Cluster and Session
        self.mock_cluster_patcher = patch('cassandra_converter.Cluster')
        self.mock_cluster = self.mock_cluster_patcher.start()

        self.mock_session = MagicMock(spec=Session)
        self.mock_cluster.return_value.connect.return_value = self.mock_session

        # Configure mocks
        mock_result = MagicMock()
        mock_result.one.return_value = None
        self.mock_session.execute.return_value = mock_result
        self.mock_session.row_factory = dict_factory

        # Create converter with mocked dependencies
        self.converter = PyCassandraConverter(
            contact_points=["test.local"],
            port=9999,
            keyspace="test_keyspace"
        )

        # Reset execute mock after initialization
        self.mock_session.execute.reset_mock()

    def tearDown(self):
        """Clean up after tests."""
        self.mock_cluster_patcher.stop()

    def test_init(self):
        """Test proper converter initialization."""
        # Create a new converter to test initialization
        fresh_mock_session = MagicMock(spec=Session)
        self.mock_cluster.return_value.connect.return_value = fresh_mock_session

        expected_keyspace_query = (
            "CREATE KEYSPACE IF NOT EXISTS test_keyspace "
            "WITH REPLICATION = { 'class' : 'SimpleStrategy', 'replication_factor' : 1 }"
        )

        new_converter = PyCassandraConverter(
            contact_points=["test.local"],
            port=9999,
            keyspace="test_keyspace"
        )

        # Check if Cluster was initialized correctly
        self.mock_cluster.assert_called_with(
            contact_points=["test.local"],
            port=9999
        )

        # Check if keyspace creation query was executed
        fresh_mock_session.execute.assert_any_call(expected_keyspace_query)

        # Check if keyspace was set
        fresh_mock_session.set_keyspace.assert_called_once_with("test_keyspace")

    def test_close(self):
        """Test proper connection closing."""
        self.converter.close()
        self.mock_cluster.return_value.shutdown.assert_called_once()

    def test_convert_primitive_types(self):
        """Test conversion of basic types."""
        # String
        self.assertEqual(self.converter.convert_to_cassandra_type("test"), "test")

        # Integer
        self.assertEqual(self.converter.convert_to_cassandra_type(42), "42")

        # Float
        self.assertEqual(self.converter.convert_to_cassandra_type(3.14), "3.14")

        # Boolean
        self.assertEqual(self.converter.convert_to_cassandra_type(True), "True")
        self.assertEqual(self.converter.convert_to_cassandra_type(False), "False")

        # None
        self.assertIsNone(self.converter.convert_to_cassandra_type(None))

        # UUID
        test_uuid = uuid.uuid4()
        self.assertEqual(self.converter.convert_to_cassandra_type(test_uuid), test_uuid)

    def test_convert_date_time(self):
        """Test date and time conversion."""
        # Date
        test_date = date(2023, 1, 15)
        result = self.converter.convert_to_cassandra_type(test_date)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)

        # Datetime
        test_datetime = datetime(2023, 1, 15, 10, 30, 45)
        result = self.converter.convert_to_cassandra_type(test_datetime)
        self.assertEqual(result, test_datetime)

    def test_convert_complex(self):
        """Test conversion of complex numbers."""
        test_complex = complex(3, 4)
        result = self.converter.convert_to_cassandra_type(test_complex)
        expected = json.dumps({"real": 3.0, "imag": 4.0, "_type": "complex"})
        self.assertEqual(result, expected)

    def test_convert_collections(self):
        """Test conversion of collections."""
        # List
        test_list = [1, "two", 3.0]
        result = self.converter.convert_to_cassandra_type(test_list)
        expected = ["1", "two", "3.0"]  # Fixed expected value
        self.assertEqual(result, expected)

        # Tuple
        test_tuple = (1, "two", 3.0)
        result = self.converter.convert_to_cassandra_type(test_tuple)
        expected = ["1", "two", "3.0"]  # Fixed expected value
        self.assertEqual(result, expected)

        # Set
        test_set = {1, 2, 3}
        result = self.converter.convert_to_cassandra_type(test_set)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)

        # Dictionary
        test_dict = {"a": 1, "b": "two", "c": 3.0}
        result = self.converter.convert_to_cassandra_type(test_dict)
        parsed_result = json.loads(result)
        self.assertEqual(parsed_result["a"], "1")
        self.assertEqual(parsed_result["b"], "two")
        self.assertEqual(parsed_result["c"], "3.0")

    def test_convert_custom_object(self):
        """Test conversion of custom object."""

        class TestObject:
            def __init__(self):
                self.name = "test"
                self.value = 42
                self.active = True

        test_obj = TestObject()
        result = self.converter.convert_to_cassandra_type(test_obj)
        parsed_result = json.loads(result)

        self.assertEqual(parsed_result["_type"], "TestObject")
        self.assertEqual(parsed_result["name"], "test")
        self.assertEqual(parsed_result["value"], "42")
        self.assertEqual(parsed_result["active"], "True")

    def test_convert_circular_reference(self):
        """Test handling circular references."""
        # Create a circular reference
        a = {}
        b = {"a": a}
        a["b"] = b

        result = self.converter.convert_to_cassandra_type(a)
        parsed_result = json.loads(result)

        # With correct circular reference handling:
        self.assertTrue("b" in parsed_result)
        self.assertTrue("a" in parsed_result["b"])
        self.assertTrue("$ref" in parsed_result["b"]["a"])
        self.assertEqual(parsed_result["b"]["a"]["$ref"], "circular_reference")

    def test_get_cassandra_type(self):
        """Test determining Cassandra types."""
        self.assertEqual(self.converter._get_cassandra_type("text"), "text")
        self.assertEqual(self.converter._get_cassandra_type(42), "bigint")
        self.assertEqual(self.converter._get_cassandra_type(3.14), "double")
        self.assertEqual(self.converter._get_cassandra_type(True), "boolean")  # Fixed
        self.assertEqual(self.converter._get_cassandra_type(uuid.uuid4()), "uuid")
        self.assertEqual(self.converter._get_cassandra_type(datetime.now()), "timestamp")
        self.assertEqual(self.converter._get_cassandra_type(date.today()), "date")
        self.assertEqual(self.converter._get_cassandra_type([1, 2, 3]), "list<text>")
        self.assertEqual(self.converter._get_cassandra_type({"a": 1}), "text")
        self.assertEqual(self.converter._get_cassandra_type(object()), "text")

    def test_table_exists(self):
        """Test checking if table exists."""
        # Configure mock
        mock_result = MagicMock()
        mock_result.one.return_value = {"table_name": "test_table"}
        self.mock_session.execute.return_value = mock_result

        # Test when table exists
        self.assertTrue(self.converter._table_exists("test_table"))

        # Test when table doesn't exist
        mock_result.one.return_value = None
        self.assertFalse(self.converter._table_exists("nonexistent_table"))

    def test_get_table_columns(self):
        """Test getting table columns."""
        # Configure mock
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            {"column_name": "id"},
            {"column_name": "name"},
            {"column_name": "value"}
        ]
        self.mock_session.execute.return_value = mock_result

        # Mock table_exists to return True
        self.converter._table_exists = lambda x: True

        columns = self.converter._get_table_columns("test_table")
        self.assertEqual(columns, {"id", "name", "value"})

    def test_get_primary_key(self):
        """Test getting primary key."""
        # Configure mock
        mock_result = MagicMock()
        mock_result.one.return_value = {"column_name": "id"}
        self.mock_session.execute.return_value = mock_result

        pk = self.converter._get_primary_key("test_table")
        self.assertEqual(pk, "id")

        # Test fallback when PK can't be determined
        mock_result.one.return_value = None
        pk = self.converter._get_primary_key("test_table")
        self.assertEqual(pk, "id")

    def test_create_table_from_dict(self):
        """Test creating table from dictionary."""
        test_data = {
            "id": uuid.uuid4(),
            "name": "test",
            "value": 42,
            "active": True,  # This is a boolean
            "created_at": datetime.now()
        }

        # Call method
        self.converter._create_table_from_dict("test_table", test_data, "id")

        # Check if CREATE TABLE query was executed
        self.assertEqual(self.mock_session.execute.call_count, 1)

        # Get the actual query
        query = self.mock_session.execute.call_args[0][0]

        # Basic query structure check
        self.assertIn("CREATE TABLE IF NOT EXISTS test_table", query)
        self.assertIn('"id" uuid PRIMARY KEY', query)
        self.assertIn('"name" text', query)
        self.assertIn('"value" bigint', query)
        self.assertIn('"active" boolean', query)  # Fixed: should be boolean
        self.assertIn('"created_at" timestamp', query)

    def test_ensure_table_columns(self):
        """Test adding missing columns to table."""
        # Configure mock for existing columns
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            {"column_name": "id"},
            {"column_name": "name"}
        ]
        self.mock_session.execute.return_value = mock_result

        # Mock table_exists to return True
        self.converter._table_exists = lambda x: True

        test_data = {
            "id": uuid.uuid4(),
            "name": "test",
            "new_field": "new value"
        }

        # Call method
        self.converter._ensure_table_columns("test_table", test_data)

        # Check if ALTER TABLE was executed for the new column
        expected_call = 'ALTER TABLE test_table ADD "new_field" text'

        # Using assert_any_call because there might be other calls
        self.mock_session.execute.assert_any_call(expected_call)

    def test_save_to_cassandra_simple_object(self):
        """Test saving a simple object."""

        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age

        test_person = Person("John", 30)

        # Configure mocks
        self.converter._table_exists = MagicMock(return_value=False)

        # Call method
        with patch.object(self.converter, '_create_table_from_dict') as mock_create_table:
            result_id = self.converter.save_to_cassandra(test_person)

            # Check if _create_table_from_dict was called
            mock_create_table.assert_called_once()

            # Check if result is a UUID
            self.assertIsInstance(result_id, uuid.UUID)

    def test_save_to_cassandra_with_custom_id(self):
        """Test saving object with custom ID."""
        test_dict = {"name": "test", "value": 42}
        custom_id = uuid.uuid4()

        # Configure mocks
        self.converter._table_exists = MagicMock(return_value=False)

        # Call method
        with patch.object(self.converter, '_create_table_from_dict') as mock_create_table:
            result_id = self.converter.save_to_cassandra(test_dict, document_id=custom_id)

            # Check if custom ID was used
            self.assertEqual(result_id, custom_id)

            # Check if table creation included the custom ID
            args = mock_create_table.call_args[0]
            self.assertEqual(args[0], "dictionary")  # table name
            self.assertIn("id", args[1])  # object dictionary
            self.assertEqual(args[1]["id"], custom_id)  # check ID value

    def test_retrieve_from_cassandra(self):
        """Test retrieving data from Cassandra."""
        # Configure mock for query results
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            {"id": uuid.uuid4(), "name": "test1", "value": 10},
            {"id": uuid.uuid4(), "name": "test2", "value": 20}
        ]
        self.mock_session.execute.return_value = mock_result

        # Mock table_exists to return True
        self.converter._table_exists = MagicMock(return_value=True)

        # Call method without query
        results = self.converter.retrieve_from_cassandra("test_table")
        self.assertEqual(len(list(results)), 2)

        # Call method with query
        query = {"name": "test1"}
        self.converter.retrieve_from_cassandra("test_table", query)

        # Check if query was executed with WHERE clause
        self.mock_session.execute.assert_called_with(
            'SELECT * FROM test_table WHERE "name" = %s',
            ["test1"]
        )

    def test_retrieve_from_nonexistent_table(self):
        """Test retrieving data from non-existent table."""
        self.converter._table_exists = MagicMock(return_value=False)
        results = self.converter.retrieve_from_cassandra("nonexistent_table")
        self.assertEqual(results, [])


if __name__ == '__main__':
    unittest.main()