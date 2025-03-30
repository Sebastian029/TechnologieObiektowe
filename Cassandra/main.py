import inspect
import json
from datetime import date, datetime
import uuid
from cassandra.cluster import Cluster
from cassandra.query import dict_factory


class PyCassandraConverter:
    def __init__(self, contact_points=["localhost"], port=9042, keyspace="default_keyspace"):
        self.cluster = Cluster(contact_points=contact_points, port=port)
        self.session = self.cluster.connect()
        self.session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS {keyspace} 
            WITH REPLICATION = {{ 'class' : 'SimpleStrategy', 'replication_factor' : 1 }}
        """)
        self.session.set_keyspace(keyspace)
        self.session.row_factory = dict_factory
        self.keyspace = keyspace

    def _table_exists(self, table_name):
        result = self.session.execute(f"""
            SELECT table_name FROM system_schema.tables 
            WHERE keyspace_name = '{self.keyspace}' AND table_name = '{table_name}'
        """)
        return bool(result.one())

    def convert_to_cassandra_type(self, obj, visited=None):
        if visited is None:
            visited = set()

        if isinstance(obj, (dict, list, tuple, set, frozenset)) and id(obj) in visited:
            return "CIRCULAR_REFERENCE"

        if isinstance(obj, (dict, list, tuple, set, frozenset)):
            visited.add(id(obj))

        # Basic types
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return str(obj) if isinstance(obj, (int, float, bool)) else obj
        elif isinstance(obj, uuid.UUID):
            return obj
        elif isinstance(obj, datetime):
            return obj
        elif isinstance(obj, date):
            return obj
        elif isinstance(obj, complex):
            return json.dumps({"real": obj.real, "imag": obj.imag, "_type": "complex"})

        # Collections - convert all elements to strings
        elif isinstance(obj, (list, tuple)):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, (set, frozenset)):
            return {str(self.convert_to_cassandra_type(item, visited)) for item in obj}
        elif isinstance(obj, dict):
            return json.dumps({str(k): self.convert_to_cassandra_type(v, visited) for k, v in obj.items()})

        # Class instances
        elif hasattr(obj, "__dict__"):
            result = {"_type": type(obj).__name__}
            for attr, value in vars(obj).items():
                result[attr] = self.convert_to_cassandra_type(value, visited)
            return result

        # Fallback
        else:
            return str(obj)

    def _get_cassandra_type(self, value):
        if value is None:
            return "text"
        if isinstance(value, (str, int, float, bool)):
            return "text"
        elif isinstance(value, uuid.UUID):
            return "uuid"
        elif isinstance(value, datetime):
            return "timestamp"
        elif isinstance(value, date):
            return "date"
        elif isinstance(value, (list, tuple, set)):
            return "list<text>"
        elif isinstance(value, dict):
            return "text"
        else:
            return "text"

    def _get_table_columns(self, table_name):
        if not self._table_exists(table_name):
            return set()
        try:
            result = self.session.execute(f"""
                SELECT column_name FROM system_schema.columns
                WHERE keyspace_name = '{self.keyspace}' AND table_name = '{table_name}'
            """)
            return {row.column_name.lower() for row in result}
        except Exception as e:
            print(f"Warning: Could not get columns for {table_name}: {e}")
            return set()

    def _create_table_from_dict(self, table_name, obj_dict, primary_key="id"):
        columns = []
        if primary_key not in obj_dict:
            obj_dict[primary_key] = uuid.uuid4()

        for key, value in obj_dict.items():
            safe_key = key.lower().replace(' ', '_')
            col_type = self._get_cassandra_type(value)
            if safe_key == primary_key:
                columns.insert(0, f'"{safe_key}" {col_type} PRIMARY KEY')
            else:
                columns.append(f'"{safe_key}" {col_type}')

        self.session.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {", ".join(columns)}
            )
        """)

    def _ensure_table_columns(self, table_name, obj_dict):
        existing_columns = self._get_table_columns(table_name)
        for key in obj_dict.keys():
            safe_key = key.lower().replace(' ', '_')
            if safe_key not in existing_columns:
                col_type = self._get_cassandra_type(obj_dict[key])
                try:
                    self.session.execute(f'ALTER TABLE {table_name} ADD "{safe_key}" {col_type}')
                except Exception as e:
                    print(f"Warning: Could not add column {safe_key}: {e}")

    def save_to_cassandra(self, obj, object_id=None):
        table_name = obj.__class__.__name__.lower()
        cassandra_obj = self.convert_to_cassandra_type(obj)

        if "id" not in cassandra_obj or cassandra_obj["id"] is None:
            cassandra_obj["id"] = object_id if object_id is not None else uuid.uuid4()

        if not self._table_exists(table_name):
            self._create_table_from_dict(table_name, cassandra_obj)
        else:
            self._ensure_table_columns(table_name, cassandra_obj)

        columns = []
        values = []
        for key, value in cassandra_obj.items():
            safe_key = key.lower().replace(' ', '_')
            columns.append(f'"{safe_key}"')
            # Ensure collections are properly formatted
            if isinstance(value, (list, set)):
                values.append(list(value) if isinstance(value, set) else value)
            else:
                values.append(value)

        query = f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(values))})
        """

        try:
            self.session.execute(query, values)
        except Exception as e:
            print(f"\nERROR DETAILS:")
            print(f"Table: {table_name}")
            print(f"Query: {query}")
            print(f"Values: {values}")
            raise RuntimeError(f"Failed to save to Cassandra: {str(e)}")

        return cassandra_obj["id"]

    def retrieve_from_cassandra(self, table_name, where_clause=None, params=None):
        if params is None:
            params = []
        query = f"SELECT * FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"
        return list(self.session.execute(query, params))

    def close(self):
        self.cluster.shutdown()


if __name__ == "__main__":
    class TestObject:
        def __init__(self):
            self.string = "Hello Cassandra"
            self.integer = 42
            self.float = 3.14159
            self.boolean = True
            self.none = None
            self.date = datetime.now()
            self.complex_number = complex(1, 2)
            self.list = [1, 2, 3]
            self.tuple = (4, 5, 6)
            self.set = {7, 8, 9}
            self.nested_dict = {'a': 1, 'b': [2, 3]}


    converter = PyCassandraConverter(keyspace="object_db")
    try:
        converter.session.execute("DROP TABLE IF EXISTS testobject")
        test_obj = TestObject()
        obj_id = converter.save_to_cassandra(test_obj)
        print(f"Successfully saved object with ID: {obj_id}")
        records = converter.retrieve_from_cassandra("testobject")
        print("Retrieved records:", records)
    finally:
        converter.close()