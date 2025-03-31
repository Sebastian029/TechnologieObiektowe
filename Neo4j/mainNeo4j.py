import inspect
from datetime import date, datetime
from neo4j import GraphDatabase
import json
from main_objects import objects_list

class Neo4jConverter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._seen_objects = set()

    def close(self):
        self.driver.close()

    def convert_to_neo4j_type(self, obj):
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        elif isinstance(obj, complex):
            return f"{obj.real}+{obj.imag}j"
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        elif isinstance(obj, (list, set, tuple)):
            if id(obj) in self._seen_objects:
                return "[Circular Reference]"
            self._seen_objects.add(id(obj))
            try:
                return [self.convert_to_neo4j_type(item) for item in obj]
            finally:
                self._seen_objects.remove(id(obj))
        elif isinstance(obj, dict):
            if id(obj) in self._seen_objects:
                return "{Circular Reference}"
            self._seen_objects.add(id(obj))
            try:
                return {k: self.convert_to_neo4j_type(v) for k, v in obj.items()}
            finally:
                self._seen_objects.remove(id(obj))
        elif hasattr(obj, "__dict__"):
            if id(obj) in self._seen_objects:
                return f"[Circular Reference: {obj.__class__.__name__}]"
            self._seen_objects.add(id(obj))
            try:
                obj_dict = vars(obj)
                return {k: self.convert_to_neo4j_type(v) for k, v in obj_dict.items()}
            finally:
                self._seen_objects.remove(id(obj))
        return str(obj)

    def save_to_neo4j(self, obj):
        self._seen_objects = set()
        obj_data = self.convert_to_neo4j_type(obj)
        
        if not isinstance(obj_data, dict):
            obj_data = {"value": obj_data}
        
        final_properties = {}
        for key, value in obj_data.items():
            if isinstance(value, (dict, list)):
                try:
                    final_properties[key] = json.dumps(value)
                except TypeError:
                    final_properties[key] = str(value)
            else:
                final_properties[key] = value
        
        label = obj.__class__.__name__
        properties = ", ".join(f"{key}: ${key}" for key in final_properties.keys())

        # Updated to use elementId() instead of id()
        query = f"CREATE (n:{label} {{{properties}}}) RETURN elementId(n)"

        with self.driver.session() as session:
            result = session.run(query, **final_properties)
            return result.single()[0]

    def retrieve_from_neo4j(self, label):
        query = f"MATCH (n:{label}) RETURN n"
        with self.driver.session() as session:
            result = session.run(query)
            nodes = []
            for record in result:
                node_properties = dict(record["n"])
                for key, value in node_properties.items():
                    if isinstance(value, str):
                        try:
                            node_properties[key] = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                nodes.append(node_properties)
            return nodes

if __name__ == "__main__":
    converter = Neo4jConverter(uri="bolt://localhost:7687", user="neo4j", password="password")
    try:
        for obj in objects_list:
            try:
                node_id = converter.save_to_neo4j(obj)
                print(f"Successfully saved {obj.__class__.__name__} with elementId: {node_id}")
            except Exception as e:
                print(f"Failed to save {obj.__class__.__name__}: {str(e)}")
    finally:
        converter.close()