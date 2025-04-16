import unittest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime
import neo4j

# Import the Neo4jConverter class
from neo4j_converter import Neo4jConverter

class TestNeo4jConverter(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a mock for the GraphDatabase.driver
        self.driver_patcher = patch('neo4j_converter.GraphDatabase')
        self.mock_graph_db = self.driver_patcher.start()

        # Set up mock driver and session
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_result = MagicMock()

        # Configure the mocks
        self.mock_graph_db.driver.return_value = self.mock_driver
        self.mock_driver.session.return_value.__enter__.return_value = self.mock_session
        self.mock_session.run.return_value = self.mock_result

        # Configure mock result to return element IDs
        self.mock_result.single.return_value = ["element_id_1"]  # Mock element ID

        # Create converter with mock driver
        self.converter = Neo4jConverter(uri="bolt://test:7687", user="test", password="test")

    def tearDown(self):
        """Tear down test fixtures after each test method."""
        self.driver_patcher.stop()

    def test_init(self):
        """Test converter initialization."""
        # Verify GraphDatabase.driver was called with correct parameters
        self.mock_graph_db.driver.assert_called_once_with(
            "bolt://test:7687",
            auth=("test", "test")
        )
        # Verify saved_nodes is initialized as empty dict
        self.assertEqual(self.converter._saved_nodes, {})

    def test_close(self):
        """Test closing the connection."""
        self.converter.close()
        self.mock_driver.close.assert_called_once()

    def test_serialize_primitive_types(self):
        """Test serialization of primitive types."""
        # Test string
        self.assertEqual(self.converter._serialize_value("test"), "test")

        # Test integer
        self.assertEqual(self.converter._serialize_value(42), 42)

        # Test float
        self.assertEqual(self.converter._serialize_value(3.14), 3.14)

        # Test boolean
        self.assertEqual(self.converter._serialize_value(True), True)
        self.assertEqual(self.converter._serialize_value(False), False)

        # Test None
        self.assertIsNone(self.converter._serialize_value(None))

    def test_serialize_date_time(self):
        """Test serialization of date and datetime objects."""
        # Test date
        test_date = date(2023, 1, 15)
        self.assertEqual(self.converter._serialize_value(test_date), "2023-01-15")

        # Test datetime
        test_datetime = datetime(2023, 1, 15, 10, 30, 45)
        self.assertEqual(self.converter._serialize_value(test_datetime), "2023-01-15T10:30:45")

    def test_serialize_complex(self):
        """Test serialization of complex numbers."""
        test_complex = complex(3, 4)
        self.assertEqual(self.converter._serialize_value(test_complex), "(3+4j)")

    def test_serialize_collections(self):
        """Test serialization of collection types."""
        # Test list
        test_list = [1, "two", 3.0]
        self.assertEqual(self.converter._serialize_value(test_list), [1, "two", 3.0])

        # Test tuple
        test_tuple = (1, "two", 3.0)
        self.assertEqual(self.converter._serialize_value(test_tuple), [1, "two", 3.0])

        # Test set
        test_set = {1, 2, 3}
        result = self.converter._serialize_value(test_set)
        self.assertIsInstance(result, list)
        self.assertCountEqual(result, [1, 2, 3])

        # Test dictionary
        test_dict = {"a": 1, "b": "two", "c": 3.0}
        self.assertEqual(self.converter._serialize_value(test_dict), test_dict)

        # Test nested collections
        nested_data = {"list": [1, 2, 3], "dict": {"a": 1, "b": 2}}
        self.assertEqual(self.converter._serialize_value(nested_data), nested_data)

    def test_is_basic_type(self):
        """Test _is_basic_type method."""
        # Basic types
        self.assertTrue(self.converter._is_basic_type("string"))
        self.assertTrue(self.converter._is_basic_type(42))
        self.assertTrue(self.converter._is_basic_type(3.14))
        self.assertTrue(self.converter._is_basic_type(True))
        self.assertTrue(self.converter._is_basic_type(None))
        self.assertTrue(self.converter._is_basic_type(date(2023, 1, 15)))
        self.assertTrue(self.converter._is_basic_type(datetime(2023, 1, 15, 10, 30)))

        # Non-basic types
        self.assertFalse(self.converter._is_basic_type([1, 2, 3]))
        self.assertFalse(self.converter._is_basic_type({"a": 1}))
        self.assertFalse(self.converter._is_basic_type((1, 2)))
        self.assertFalse(self.converter._is_basic_type({1, 2, 3}))
        self.assertFalse(self.converter._is_basic_type(complex(1, 2)))

        # Custom object
        class TestObj:
            pass

        self.assertFalse(self.converter._is_basic_type(TestObj()))

    def test_create_node(self):
        """Test _create_node method."""

        class TestObject:
            def __init__(self):
                self.name = "test"
                self.value = 42
                self.active = True

        test_obj = TestObject()

        # Call method
        result = self.converter._create_node(test_obj)

        # Verify session.run was called with correct query and parameters
        expected_query = "CREATE (n:TestObject {name: $name, value: $value, active: $active}) RETURN elementId(n)"
        self.mock_session.run.assert_called_once()

        call_args = self.mock_session.run.call_args
        actual_query = call_args[0][0]
        actual_params = call_args[1]

        # Check query structure (ignoring whitespace differences)
        self.assertEqual(
            ''.join(actual_query.split()),
            ''.join(expected_query.split())
        )

        # Check parameters
        self.assertEqual(actual_params["name"], "test")
        self.assertEqual(actual_params["value"], 42)
        self.assertEqual(actual_params["active"], True)

        # Check return value
        self.assertEqual(result, "element_id_1")

        # Check that object ID was saved
        self.assertIn(id(test_obj), self.converter._saved_nodes)
        self.assertEqual(self.converter._saved_nodes[id(test_obj)], "element_id_1")

    def test_create_node_duplicate(self):
        """Test _create_node with an already saved object."""

        class TestObject:
            def __init__(self):
                self.name = "test"

        test_obj = TestObject()
        obj_id = id(test_obj)

        # Pre-populate _saved_nodes
        self.converter._saved_nodes[obj_id] = "existing_element_id"

        # Call method
        result = self.converter._create_node(test_obj)

        # Verify no database call was made
        self.mock_session.run.assert_not_called()

        # Check return value is the existing ID
        self.assertEqual(result, "existing_element_id")

    def test_create_relationship(self):
        """Test _create_relationship method."""

        class Parent:
            def __init__(self):
                self.name = "parent"

        class Child:
            def __init__(self):
                self.name = "child"

        parent = Parent()
        child = Child()

        # Set up saved nodes
        self.converter._saved_nodes[id(parent)] = "parent_id"
        self.converter._saved_nodes[id(child)] = "child_id"

        # Call method
        self.converter._create_relationship(parent, child, "CHILD")

        # Verify session.run was called with correct query and parameters
        expected_query = """
        MATCH (a) WHERE elementId(a) = $from_id
        MATCH (b) WHERE elementId(b) = $to_id
        MERGE (a)-[r:HAS_CHILD]->(b)
        """

        self.mock_session.run.assert_called_once()

        call_args = self.mock_session.run.call_args

        # Check parameters
        self.assertEqual(call_args[1]["from_id"], "parent_id")
        self.assertEqual(call_args[1]["to_id"], "child_id")

    def test_create_relationship_missing_node(self):
        """Test _create_relationship with missing node IDs."""
        obj1 = object()
        obj2 = object()

        # Only save one of the objects
        self.converter._saved_nodes[id(obj1)] = "obj1_id"

        # Call method
        self.converter._create_relationship(obj1, obj2, "TEST")

        # Verify no database call was made
        self.mock_session.run.assert_not_called()

    def test_save_simple_object(self):
        """Test save method with a simple object."""

        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age

        # Create a test object
        test_person = Person("John", 30)

        # Mock _create_node and _recursive_save to track calls
        with patch.object(self.converter, '_create_node') as mock_create_node, \
                patch.object(self.converter, '_recursive_save',
                             wraps=self.converter._recursive_save) as mock_recursive_save:
            # Configure _create_node mock
            mock_create_node.return_value = "person_node_id"

            # Call save
            self.converter.save(test_person)

            # Verify that _saved_nodes was reset
            self.assertEqual(len(self.converter._saved_nodes), 0)

            # Verify _recursive_save was called with correct parameters
            mock_recursive_save.assert_called_with(test_person)

    def test_recursive_save_with_simple_object(self):
        """Test _recursive_save with an object having basic type attributes."""

        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age

        test_person = Person("John", 30)

        # Mock methods
        with patch.object(self.converter, '_create_node') as mock_create_node, \
                patch.object(self.converter, '_create_relationship') as mock_create_rel:
            # Call method
            self.converter._recursive_save(test_person)

            # Verify _create_node was called once
            mock_create_node.assert_called_once_with(test_person)

            # Verify _create_relationship was NOT called (no complex attributes)
            mock_create_rel.assert_not_called()

    def test_recursive_save_with_complex_attributes(self):
        """Test _recursive_save with object having nested objects."""

        class Address:
            def __init__(self, street, city):
                self.street = street
                self.city = city

        class Person:
            def __init__(self, name, address):
                self.name = name
                self.address = address
                self.friends = []

        address = Address("123 Main St", "Anytown")
        friend1 = Person("Friend1", None)
        friend2 = Person("Friend2", None)

        test_person = Person("John", address)
        test_person.friends = [friend1, friend2]

        # Mock methods
        with patch.object(self.converter, '_create_node') as mock_create_node, \
                patch.object(self.converter, '_create_relationship') as mock_create_rel:
            # Configure mock to assign IDs
            mock_create_node.side_effect = ["person_id", "address_id", "friend1_id", "friend2_id"]

            # Call method
            self.converter._recursive_save(test_person)

            # Verify correct nodes were created
            mock_create_node.assert_has_calls([
                call(test_person),
                call(address),
                call(friend1),
                call(friend2)
            ], any_order=False)

            # Verify relationships were created correctly
            mock_create_rel.assert_has_calls([
                call(test_person, address, "ADDRESS"),
                call(test_person, friend1, "FRIENDS"),
                call(test_person, friend2, "FRIENDS")
            ], any_order=True)  # Order may vary for lists


if __name__ == '__main__':
    unittest.main()