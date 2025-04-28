from datetime import date, datetime
from neo4j import GraphDatabase

class Neo4jConverter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._saved_nodes = {}  # id(obj) -> Neo4j elementId

    def close(self):
        self.driver.close()

    def _create_node(self, obj):
        obj_id = id(obj)
        if obj_id in self._saved_nodes:
            return self._saved_nodes[obj_id]

        # Używamy nazwy klasy jako etykiety
        label = obj.__class__.__name__
        
        properties_str = ", ".join(f"{k}={repr(v)}" for k, v in vars(obj).items() if isinstance(v, (str, int, float, bool, type(None), date, datetime)))
    
        properties = {
        '_python_type': label,
        '_repr': f"{label}({properties_str})",  # Auto-repr
        }
        # Dodajemy właściwości obiektu
        for attr, value in vars(obj).items():
            if isinstance(value, (str, int, float, bool, type(None), date, datetime)):
                properties[attr] = value

        query = f"""
        CREATE (n:{label} $props)
        RETURN elementId(n)
        """
        
        with self.driver.session() as session:
            result = session.run(query, props=properties)
            element_id = result.single()[0]
            self._saved_nodes[obj_id] = element_id
            return element_id

    def _create_relationship(self, from_obj, to_obj, rel_type):
        from_id = self._saved_nodes.get(id(from_obj))
        to_id = self._saved_nodes.get(id(to_obj))
        if not from_id or not to_id:
            return

        query = """
        MATCH (a) WHERE elementId(a) = $from_id
        MATCH (b) WHERE elementId(b) = $to_id
        MERGE (a)-[r:%s]->(b)
        """ % rel_type
        
        with self.driver.session() as session:
            session.run(query, from_id=from_id, to_id=to_id)

    def save(self, obj):
        self._saved_nodes = {}
        self._save_object(obj)

    def _save_object(self, obj, processed=None):
        if processed is None:
            processed = set()
        
        obj_id = id(obj)
        if obj_id in processed:
            return
        processed.add(obj_id)

        # Najpierw tworzymy węzeł
        self._create_node(obj)

        # Potem przetwarzamy zagnieżdżone obiekty
        for attr, value in vars(obj).items():
            if hasattr(value, "__dict__"):  # Dla obiektów
                self._save_object(value, processed)
                self._create_relationship(obj, value, f"HAS_{attr.upper()}")
            elif isinstance(value, (list, tuple, set)):  # Dla kolekcji
                for item in value:
                    if hasattr(item, "__dict__"):
                        self._save_object(item, processed)
                        self._create_relationship(obj, item, f"HAS_{attr.upper()}")
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
