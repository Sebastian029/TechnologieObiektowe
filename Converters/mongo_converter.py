import inspect
from datetime import date, datetime
from pymongo import MongoClient



class PyMongoConverter:
    def __init__(self, connection_string="mongodb://localhost:27017/", db_name="default_db"):
        self.client = MongoClient(connection_string)
        self.db = self.client[db_name]

    def convert_to_mongo_type(self, obj, visited=None):
        if visited is None:
            visited = set()

        if isinstance(obj, (dict, list, tuple, set, frozenset)) and id(obj) in visited:
            return {"$ref": "circular_reference"}

        if isinstance(obj, (dict, list, tuple, set, frozenset)):
            visited.add(id(obj))

        if isinstance(obj, str):
            return obj
        elif isinstance(obj, int):
            return obj
        elif isinstance(obj, float):
            return obj
        elif isinstance(obj, bool):
            return obj
        elif obj is None:
            return None
        elif isinstance(obj, date) and not isinstance(obj, datetime):
            return datetime(obj.year, obj.month, obj.day)
        elif isinstance(obj, complex):
            return {"real": obj.real, "imag": obj.imag, "_type": "complex"}
        elif isinstance(obj, (list, tuple)):
            return [self.convert_to_mongo_type(item, visited) for item in obj]
        elif isinstance(obj, (set, frozenset)):
            return [self.convert_to_mongo_type(item, visited) for item in obj]
        elif isinstance(obj, dict):
            return {str(k): self.convert_to_mongo_type(v, visited) for k, v in obj.items()}
        elif hasattr(obj, "__dict__"):
            result = {"_type": type(obj).__name__}
            for attr, value in vars(obj).items():
                result[attr] = self.convert_to_mongo_type(value, visited)
            return result
        elif inspect.isclass(obj):
            return {"_type": "class", "name": obj.__name__}
        else:
            return {"_type": "unknown", "repr": repr(obj), "type_name": type(obj).__name__}

    def save_to_mongodb(self, obj, document_id=None):
        collection = self.db[obj.__class__.__name__.lower()]
        mongo_obj = self.convert_to_mongo_type(obj)
        if document_id is not None:
            mongo_obj["_id"] = document_id

        result = collection.insert_one(mongo_obj)
        return result.inserted_id

    def close(self):
        self.client.close()

if __name__ == "__main__":
    from example_objects import objects_list

    converter = PyMongoConverter(
        connection_string="mongodb://localhost:27017/",
        db_name="object_db"
    )

    try:
        for obj in objects_list:
            converter.save_to_mongodb(obj)

    finally:
        converter.close()

