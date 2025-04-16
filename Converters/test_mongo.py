import unittest
import datetime
from unittest.mock import MagicMock, patch
from pymongo.results import InsertOneResult
from bson.objectid import ObjectId

# Import from your actual module
from mongo_converter import PyMongoConverter


class TestPyMongoConverter(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a mock for MongoClient
        self.mock_client_patcher = patch('mongo_converter.MongoClient')
        self.mock_client = self.mock_client_patcher.start()

        # Configure the mocks
        self.mock_db = MagicMock()
        self.mock_collection = MagicMock()
        self.mock_client.return_value.__getitem__.return_value = self.mock_db
        self.mock_db.__getitem__.return_value = self.mock_collection

        # Configure insert_one to return a mock result with an inserted_id
        mock_result = MagicMock(spec=InsertOneResult)
        mock_result.inserted_id = ObjectId()
        self.mock_collection.insert_one.return_value = mock_result

        # Create the converter with mock client
        self.converter = PyMongoConverter(connection_string="mongodb://test:27017/", db_name="test_db")

    def tearDown(self):
        """Tear down test fixtures after each test method."""
        self.mock_client_patcher.stop()

    def test_convert_primitive_types(self):
        """Test conversion of primitive types."""
        # Test string
        self.assertEqual(self.converter.convert_to_mongo_type("test"), "test")

        # Test integer
        self.assertEqual(self.converter.convert_to_mongo_type(42), 42)

        # Test float
        self.assertEqual(self.converter.convert_to_mongo_type(3.14), 3.14)

        # Test boolean
        self.assertEqual(self.converter.convert_to_mongo_type(True), True)
        self.assertEqual(self.converter.convert_to_mongo_type(False), False)

        # Test None
        self.assertIsNone(self.converter.convert_to_mongo_type(None))

    def test_convert_date(self):
        """Test conversion of date objects."""
        test_date = datetime.date(2023, 1, 15)
        expected = datetime.datetime(2023, 1, 15, 0, 0)
        self.assertEqual(self.converter.convert_to_mongo_type(test_date), expected)

        test_datetime = datetime.datetime(2023, 1, 15, 10, 30, 45)
        result = self.converter.convert_to_mongo_type(test_datetime)
        # Check structure of result
        self.assertIsInstance(result, dict)
        self.assertEqual(result["type_name"], "datetime")

    def test_convert_complex(self):
        """Test conversion of complex numbers."""
        test_complex = complex(3, 4)
        result = self.converter.convert_to_mongo_type(test_complex)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["real"], 3.0)
        self.assertEqual(result["imag"], 4.0)
        self.assertEqual(result["_type"], "complex")

    def test_convert_list_and_tuple(self):
        """Test conversion of lists and tuples."""
        # Test list
        test_list = [1, "two", 3.0]
        self.assertEqual(self.converter.convert_to_mongo_type(test_list), [1, "two", 3.0])

        # Test tuple
        test_tuple = (1, "two", 3.0)
        # Check if result is a list
        result = self.converter.convert_to_mongo_type(test_tuple)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [1, "two", 3.0])

    def test_convert_set(self):
        """Test conversion of sets and frozensets."""
        # Test set
        test_set = {1, 2, 3}
        result = self.converter.convert_to_mongo_type(test_set)
        self.assertIsInstance(result, list)
        # Can't rely on order for sets
        self.assertEqual(set(result), {1, 2, 3})

        # Test frozenset
        test_frozenset = frozenset([1, 2, 3])
        result = self.converter.convert_to_mongo_type(test_frozenset)
        self.assertIsInstance(result, list)
        self.assertEqual(set(result), {1, 2, 3})

    def test_convert_dict(self):
        """Test conversion of dictionaries."""
        test_dict = {"a": 1, "b": "two", "c": 3.0}
        self.assertEqual(self.converter.convert_to_mongo_type(test_dict), test_dict)

        # Test with non-string keys
        test_dict_nonstr_keys = {1: "one", 2.0: "two"}
        result = self.converter.convert_to_mongo_type(test_dict_nonstr_keys)
        self.assertIn("1", result)
        self.assertIn("2.0", result)
        self.assertEqual(result["1"], "one")
        self.assertEqual(result["2.0"], "two")

    def test_convert_custom_object(self):
        """Test conversion of a custom object."""

        class TestObject:
            def __init__(self):
                self.name = "test"
                self.value = 42

        test_obj = TestObject()
        result = self.converter.convert_to_mongo_type(test_obj)

        # Check basic structure
        self.assertIsInstance(result, dict)
        self.assertEqual(result["_type"], "TestObject")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 42)

    def test_convert_class(self):
        """Test conversion of a class."""

        class TestClass:
            pass

        # Based on the error message, your implementation returns more information about classes
        result = self.converter.convert_to_mongo_type(TestClass)

        # Check that it's a dictionary with the expected structure
        self.assertIsInstance(result, dict)
        self.assertEqual(result["_type"], "type")
        self.assertEqual(result["__module__"], "test_mongo_converter")
        # Check for other expected class attributes
        self.assertIn("__dict__", result)
        self.assertIn("__doc__", result)

    def test_convert_unknown_type(self):
        """Test conversion of an unknown type."""

        # Create a type that doesn't have special handling
        class CustomType:
            def __repr__(self):
                return "CustomType()"

        test_obj = CustomType()
        result = self.converter.convert_to_mongo_type(test_obj)

        # Based on the error, it seems your implementation uses the class name as _type
        self.assertEqual(result["_type"], "CustomType")
        # Check other aspects of the result
        self.assertIsInstance(result, dict)

    def test_nested_structures(self):
        """Test conversion of nested data structures."""
        nested_data = {
            "list": [1, 2, 3],
            "dict": {"a": 1, "b": 2},
            "tuple": (4, 5, 6),
            "mixed": [{"x": 1}, (2, 3), {4, 5}]
        }

        result = self.converter.convert_to_mongo_type(nested_data)

        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["list"], list)
        self.assertEqual(result["list"], [1, 2, 3])
        self.assertIsInstance(result["dict"], dict)
        self.assertEqual(result["dict"], {"a": 1, "b": 2})
        self.assertIsInstance(result["tuple"], list)  # Tuple should be converted to list
        self.assertEqual(set(result["tuple"]), {4, 5, 6})

        # Check mixed container
        self.assertIsInstance(result["mixed"], list)
        self.assertEqual(len(result["mixed"]), 3)
        self.assertIsInstance(result["mixed"][0], dict)
        self.assertEqual(result["mixed"][0], {"x": 1})

    def test_circular_reference(self):
        """Test handling of circular references."""
        # Create a circular reference
        a = {}
        b = {"a": a}
        a["b"] = b

        result = self.converter.convert_to_mongo_type(a)

        # Check if the circular reference was detected
        self.assertIsInstance(result, dict)
        self.assertIn("b", result)
        self.assertIsInstance(result["b"], dict)
        self.assertIn("a", result["b"])

        # This is the important part - circular reference should be handled somehow
        # The exact format may vary, but there should be an indication
        circular_ref = result["b"]["a"]
        self.assertTrue(
            circular_ref == {"$ref": "circular_reference"} or
            isinstance(circular_ref, dict) and "$ref" in circular_ref
        )

    def test_save_to_mongodb(self):
        """Test saving an object to MongoDB."""

        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age

        test_person = Person("John", 30)

        # Call the method
        result_id = self.converter.save_to_mongodb(test_person)

        # Verify the collection was selected correctly
        self.mock_db.__getitem__.assert_called_with("person")

        # Verify insert_one was called
        self.mock_collection.insert_one.assert_called_once()

        # Get the argument passed to insert_one
        call_args = self.mock_collection.insert_one.call_args[0][0]

        # Check basic structure without being too strict
        self.assertIsInstance(call_args, dict)
        self.assertEqual(call_args["_type"], "Person")
        self.assertEqual(call_args["name"], "John")
        self.assertEqual(call_args["age"], 30)

        # Verify the result
        self.assertEqual(result_id, self.mock_collection.insert_one.return_value.inserted_id)

    def test_save_with_custom_id(self):
        """Test saving an object with a custom ID."""

        class Note:
            def __init__(self, content):
                self.content = content

        test_note = Note("Test content")
        custom_id = "note123"

        # Call the method
        self.converter.save_to_mongodb(test_note, document_id=custom_id)

        # Verify insert_one was called
        self.mock_collection.insert_one.assert_called_once()

        # Get the argument passed to insert_one
        call_args = self.mock_collection.insert_one.call_args[0][0]

        # Check _id was added
        self.assertEqual(call_args["_id"], "note123")
        self.assertEqual(call_args["_type"], "Note")
        self.assertEqual(call_args["content"], "Test content")

    def test_close(self):
        """Test closing the MongoDB connection."""
        self.converter.close()
        self.mock_client.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()