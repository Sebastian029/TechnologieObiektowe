from datetime import date, datetime
from neo4j import GraphDatabase

class Neo4jConverter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._saved_nodes = {}  # id(obj) -> Neo4j elementId

    def close(self):
        self.driver.close()

    def _serialize_value(self, value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        elif isinstance(value, (date, datetime)):
            return value.isoformat()
        elif isinstance(value, complex):
            return str(value)
        elif isinstance(value, (list, tuple, set)):
            return [self._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return str(value)

    def _create_node(self, obj):
        obj_id = id(obj)
        if obj_id in self._saved_nodes:
            return self._saved_nodes[obj_id]  # Avoid duplicates

        label = obj.__class__.__name__
        properties = {}
        for attr, value in vars(obj).items():
            if self._is_basic_type(value):
                properties[attr] = self._serialize_value(value)

        prop_keys = ", ".join(f"{k}: ${k}" for k in properties)
        query = f"CREATE (n:{label} {{{prop_keys}}}) RETURN elementId(n)"

        with self.driver.session() as session:
            result = session.run(query, **properties)
            element_id = result.single()[0]
            self._saved_nodes[obj_id] = element_id
            return element_id

    def _create_relationship(self, from_obj, to_obj, rel_type):
        from_id = self._saved_nodes.get(id(from_obj))
        to_id = self._saved_nodes.get(id(to_obj))
        if not from_id or not to_id:
            return

        query = f"""
        MATCH (a) WHERE elementId(a) = $from_id
        MATCH (b) WHERE elementId(b) = $to_id
        MERGE (a)-[r:HAS_{rel_type}]->(b)
        """
        with self.driver.session() as session:
            session.run(query, from_id=from_id, to_id=to_id)

    def _is_basic_type(self, val):
        return isinstance(val, (str, int, float, bool, type(None), datetime, date))

    def save(self, obj):
        self._saved_nodes = {}
        self._recursive_save(obj)

    def _recursive_save(self, obj, parent=None, rel_type=None, processed=None):
        if processed is None:
            processed = set()
        obj_id = id(obj)
        if obj_id in processed:
            return
        processed.add(obj_id)

        if obj_id in self._saved_nodes:
            if parent and rel_type:
                self._create_relationship(parent, obj, rel_type)
            return

        self._create_node(obj)

        for attr, value in vars(obj).items():
            if self._is_basic_type(value):
                continue
            elif isinstance(value, (list, set, tuple)):
                for item in value:
                    if not self._is_basic_type(item):
                        self._recursive_save(item, obj, attr.upper(), processed)
                        self._create_relationship(obj, item, attr.upper())
            elif isinstance(value, dict):
                for item in value.values():
                    if not self._is_basic_type(item):
                        self._recursive_save(item, obj, attr.upper(), processed)
                        self._create_relationship(obj, item, attr.upper())
            elif hasattr(value, "__dict__"):
                self._recursive_save(value, obj, attr.upper(), processed)
                self._create_relationship(obj, value, attr.upper())

if __name__ == "__main__":
    from objects import objects_list

    converter = Neo4jConverter(uri="bolt://localhost:7687", user="neo4j", password="password")
    try:
        for obj in objects_list:
            print(f"Saving {obj.__class__.__name__}...")
            converter.save(obj)
        print("SUCCESFUL")
    finally:
        converter.close()
