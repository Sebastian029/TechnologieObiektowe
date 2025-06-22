import inspect
import json
import uuid
from datetime import date, datetime
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
            return {"$ref": "circular_reference"}

        if isinstance(obj, (dict, list, tuple, set, frozenset)):
            visited.add(id(obj))

        if isinstance(obj, str):
            return obj
        elif isinstance(obj, bool):
            return obj
        elif isinstance(obj, int):
            return obj
        elif isinstance(obj, float):
            return obj
        elif obj is None:
            return None
        elif isinstance(obj, uuid.UUID):
            return obj
        elif isinstance(obj, datetime):
            return obj
        elif isinstance(obj, date) and not isinstance(obj, datetime):
            return datetime(obj.year, obj.month, obj.day)
        elif isinstance(obj, complex):
            return {"real": str(obj.real), "imag": str(obj.imag), "_type": "complex"}

        elif isinstance(obj, list):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, tuple):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, set):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, frozenset):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, dict):
            converted_dict = {}
            for k, v in obj.items():
                if isinstance(v, datetime):
                    converted_dict[str(k)] = v.isoformat()
                elif isinstance(v, date) and not isinstance(v, datetime):
                    converted_dict[str(k)] = v.isoformat()
                else:
                    converted_dict[str(k)] = str(self.convert_to_cassandra_type(v, visited))
            return converted_dict

        elif hasattr(obj, "__dict__"):
            result = {"_type": type(obj).__name__}
            for attr, value in vars(obj).items():
                if isinstance(value, datetime):
                    result[attr] = value.isoformat()
                elif isinstance(value, date) and not isinstance(value, datetime):
                    result[attr] = value.isoformat()
                else:
                    result[attr] = self.convert_to_cassandra_type(value, visited)
            return json.dumps(result)

        elif inspect.isclass(obj):
            return json.dumps({"_type": "class", "name": obj.__name__})

        else:
            return json.dumps({"_type": "unknown", "repr": repr(obj), "type_name": type(obj).__name__})

    def _get_cassandra_type(self, value):
        if value is None:
            return "text"
        if isinstance(value, str):
            return "text"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, uuid.UUID):
            return "uuid"
        elif isinstance(value, datetime):
            return "timestamp"
        elif isinstance(value, date):
            return "date"
        elif isinstance(value, list):
            return "list<text>"
        elif isinstance(value, tuple):
            return "tuple<text>"
        elif isinstance(value, set):
            return "set<text>"
        elif isinstance(value, frozenset):
            return "frozen<set<text>>"
        elif isinstance(value, dict):
            return "map<text,text>"
        elif isinstance(value, complex):
            return "map<text,text>"
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
            return {row["column_name"].lower() for row in result}
        except Exception as e:
            print(f"Warning: Could not get columns for {table_name}: {e}")
            return set()

    def _get_primary_key(self, table_name):
        try:
            result = self.session.execute(f"""
                SELECT column_name FROM system_schema.columns
                WHERE keyspace_name = '{self.keyspace}' AND table_name = '{table_name}'
                AND kind = 'partition_key'
                ALLOW FILTERING
            """)
            pk_row = result.one()
            return pk_row["column_name"] if pk_row else "id"
        except Exception as e:
            print(f"Warning: Could not get primary key for {table_name}: {e}")
            return "id"

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

    def save_to_cassandra(self, obj, document_id=None):
        if isinstance(obj, dict):
            table_name = "dictionary"
        elif hasattr(obj, "__class__"):
            table_name = obj.__class__.__name__.lower()
        else:
            table_name = type(obj).__name__.lower()

        cassandra_obj = {}

        if hasattr(obj, "__dict__"):
            for attr, value in vars(obj).items():
                cassandra_obj[attr] = self.convert_to_cassandra_type(value)
        else:
            cassandra_obj = {"value": self.convert_to_cassandra_type(obj)}

        if document_id is not None:
            cassandra_obj["id"] = document_id
        elif "id" not in cassandra_obj:
            cassandra_obj["id"] = uuid.uuid4()

        cassandra_obj["_type"] = type(obj).__name__

        if not self._table_exists(table_name):
            self._create_table_from_dict(table_name, cassandra_obj, primary_key="id")
            primary_key = "id"
        else:
            primary_key = self._get_primary_key(table_name)
            if primary_key not in cassandra_obj:
                cassandra_obj[primary_key] = uuid.uuid4()

            self._ensure_table_columns(table_name, cassandra_obj)

        columns = []
        values = []
        for key, value in cassandra_obj.items():
            safe_key = key.lower().replace(' ', '_')
            columns.append(f'"{safe_key}"')
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

    def retrieve_from_cassandra(self, collection_name, query=None):
        if not self._table_exists(collection_name):
            return []

        cql_query = f"SELECT * FROM {collection_name}"
        params = []

        if query and isinstance(query, dict):
            where_clauses = []
            for key, value in query.items():
                safe_key = key.lower().replace(' ', '_')
                where_clauses.append(f'"{safe_key}" = %s')
                params.append(value)

            if where_clauses:
                cql_query += f" WHERE {' AND '.join(where_clauses)}"

        return list(self.session.execute(cql_query, params))

    def close(self):
        self.cluster.shutdown()


if __name__ == "__main__":
    from objects import objects_list

    converter = PyCassandraConverter(keyspace="object_db")

    try:
        for obj in objects_list:
            converter.save_to_cassandra(obj)

    finally:
        converter.close()
