import inspect
from datetime import date, datetime
from pymongo import MongoClient

from MongoDB.objects import objects_list


class PyMongoConverter:
    def __init__(self, connection_string="mongodb://localhost:27017/", db_name="default_db"):
        self.client = MongoClient(connection_string)
        self.db = self.client[db_name]

    def convert_to_mongo_type(self, obj, visited=None):
        """
        str -> String
        list/tuple -> Array
        dict -> Object
        int -> Int64
        float -> Double
        complex -> Object
        bool -> Boolean
        set/frozenset -> Array
        None -> Null
        date/datetime -> Date
        """
        if visited is None:
            visited = set()

        # Check for circular reference
        if isinstance(obj, (dict, list, tuple, set, frozenset)) and id(obj) in visited:
            return {"$ref": "circular_reference"}

        # Add complex objects to visited
        if isinstance(obj, (dict, list, tuple, set, frozenset)):
            visited.add(id(obj))

        # Basic types
        if isinstance(obj, str):
            # String -> String (no change needed)
            return obj
        elif isinstance(obj, int):
            # int -> Int64 (no change needed)
            return obj
        elif isinstance(obj, float):
            # float -> Double (no change needed)
            return obj
        elif isinstance(obj, bool):
            # bool -> Boolean (no change needed)
            return obj
        elif obj is None:
            # None -> Null (no change needed)
            return None
        elif isinstance(obj, date) and not isinstance(obj, datetime):
            # date -> convert to datetime at midnight
            return datetime(obj.year, obj.month, obj.day)
        elif isinstance(obj, complex):
            # complex -> Object
            return {"real": obj.real, "imag": obj.imag, "_type": "complex"}

        # Collections
        elif isinstance(obj, (list, tuple)):
            # list/tuple -> Array
            return [self.convert_to_mongo_type(item, visited) for item in obj]
        elif isinstance(obj, (set, frozenset)):
            # set/frozenset -> Array
            return [self.convert_to_mongo_type(item, visited) for item in obj]
        elif isinstance(obj, dict):
            # dict -> Object
            return {str(k): self.convert_to_mongo_type(v, visited) for k, v in obj.items()}

        # Class instances
        elif hasattr(obj, "__dict__"):
            # Convert object attributes to dictionary
            result = {"_type": type(obj).__name__}
            for attr, value in vars(obj).items():
                result[attr] = self.convert_to_mongo_type(value, visited)
            return result

        # Classes
        elif inspect.isclass(obj):
            return {"_type": "class", "name": obj.__name__}

        # Handle other types by their string representation
        else:
            return {"_type": "unknown", "repr": repr(obj), "type_name": type(obj).__name__}

    def save_to_mongodb(self, obj, document_id=None):
        collection = self.db[obj.__class__.__name__.lower()]

        # Convert the object to MongoDB compatible format
        mongo_obj = self.convert_to_mongo_type(obj)

        # Add _id if provided
        if document_id is not None:
            mongo_obj["_id"] = document_id

        # Insert into MongoDB
        result = collection.insert_one(mongo_obj)
        return result.inserted_id

    def retrieve_from_mongodb(self, collection_name, query=None):
        collection = self.db[collection_name]
        if query is None:
            query = {}
        return list(collection.find(query))

    def close(self):
        self.client.close()


# Example usage
if __name__ == "__main__":
    converter = PyMongoConverter(
        connection_string="mongodb://localhost:27017/",
        db_name="object_db"
    )

    try:
        for obj in objects_list:
            converter.save_to_mongodb(obj)

    finally:
        converter.close()

