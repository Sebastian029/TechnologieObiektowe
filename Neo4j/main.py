from neo4j import GraphDatabase

class Neo4jConverter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._saved_nodes = {}

    def close(self):
        self.driver.close()

    def _create_node(self, obj):
        obj_id = id(obj)
        if obj_id in self._saved_nodes:
            return self._saved_nodes[obj_id]

        label = obj.__class__.__name__

        def convert_value(v):
            if isinstance(v, complex):
                return str(v)
            return v

        if isinstance(obj, (str, int, float, complex, bool, type(None))):
            properties = {
                '_python_type': label,
                '_repr': repr(obj),
                'value': convert_value(obj)
            }
        else:
            properties_str = ", ".join(f"{k}={repr(convert_value(v))}" for k, v in vars(obj).items()
                                       if isinstance(v, (str, int, float, bool, type(None), complex)))

            properties = {
                '_python_type': label,
                '_repr': f"{label}({properties_str})",
            }

            for attr, value in vars(obj).items():
                if isinstance(value, (str, int, float, bool, type(None), complex)):
                    properties[attr] = convert_value(value)

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

        self._create_node(obj)

        if not hasattr(obj, '__dict__'):
            return

        for attr, value in vars(obj).items():
            if hasattr(value, "__dict__"):
                self._save_object(value, processed)
                self._create_relationship(obj, value, f"HAS_{attr.upper()}")
            elif isinstance(value, (list, tuple, set, frozenset)):
                for item in value:
                    if hasattr(item, "__dict__"):
                        self._save_object(item, processed)
                        self._create_relationship(obj, item, f"HAS_{attr.upper()}")
                    elif isinstance(item, (str, int, float, complex, bool, type(None))):
                        self._save_object(item, processed)
                        self._create_relationship(obj, item, f"HAS_{attr.upper()}")
            elif isinstance(value, dict):
                for item in value.values():
                    if hasattr(item, "__dict__"):
                        self._save_object(item, processed)
                        self._create_relationship(obj, item, f"HAS_{attr.upper()}")
                    elif isinstance(item, (str, int, float, complex, bool, type(None))):
                        self._save_object(item, processed)
                        self._create_relationship(obj, item, f"HAS_{attr.upper()}")
