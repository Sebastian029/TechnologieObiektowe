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
        """
        Convert Python objects to Cassandra-compatible format:
        str -> text
        int/float/bool -> text (as string)
        None -> NULL
        date -> date
        datetime -> timestamp
        complex -> text (as JSON)
        list/tuple/set -> list<text>
        dict -> text (as JSON)
        objects -> text (as JSON)
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
            return obj
        elif isinstance(obj, (int, float, bool)):
            return str(obj)
        elif obj is None:
            return None
        elif isinstance(obj, uuid.UUID):
            return obj
        elif isinstance(obj, datetime):
            # For Cassandra insertion, return the datetime object directly
            # For JSON serialization (in dicts), it will be handled in the dict case
            return obj
        elif isinstance(obj, date) and not isinstance(obj, datetime):
            return datetime(obj.year, obj.month, obj.day)
        elif isinstance(obj, complex):
            return json.dumps({"real": obj.real, "imag": obj.imag, "_type": "complex"})

        # Collections
        elif isinstance(obj, (list, tuple)):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, (set, frozenset)):
            return [str(self.convert_to_cassandra_type(item, visited)) for item in obj]
        elif isinstance(obj, dict):
            # Convert each value in the dictionary, handling datetime objects specially
            converted_dict = {}
            for k, v in obj.items():
                if isinstance(v, datetime):
                    # Convert datetime to ISO format string for JSON serialization
                    converted_dict[str(k)] = v.isoformat()
                elif isinstance(v, date) and not isinstance(v, datetime):
                    # Convert date to ISO format string for JSON serialization
                    converted_dict[str(k)] = v.isoformat()
                else:
                    converted_dict[str(k)] = self.convert_to_cassandra_type(v, visited)
            return json.dumps(converted_dict)

        # Class instances
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

        # Classes
        elif inspect.isclass(obj):
            return json.dumps({"_type": "class", "name": obj.__name__})

        # Fallback for other types
        else:
            return json.dumps({"_type": "unknown", "repr": repr(obj), "type_name": type(obj).__name__})

    def _get_cassandra_type(self, value):
        if value is None:
            return "text"
        if isinstance(value, str):
            return "text"
        elif isinstance(value, int):
            return "bigint"
        elif isinstance(value, float):
            return "double"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, uuid.UUID):
            return "uuid"
        elif isinstance(value, datetime):
            return "timestamp"
        elif isinstance(value, date):
            return "date"
        elif isinstance(value, (list, tuple, set)):
            return "list<text>"
        elif isinstance(value, dict):
            return "text"  # JSON stored as text
        else:
            return "text"  # Default to text for complex objects

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
        """Get the primary key column name for an existing table"""
        try:
            result = self.session.execute(f"""
                SELECT column_name FROM system_schema.columns
                WHERE keyspace_name = '{self.keyspace}' AND table_name = '{table_name}'
                AND kind = 'partition_key'
            """)
            pk_row = result.one()
            return pk_row["column_name"] if pk_row else "id"
        except Exception as e:
            print(f"Warning: Could not get primary key for {table_name}: {e}")
            return "id"

    def _create_table_from_dict(self, table_name, obj_dict, primary_key="id"):
        columns = []

        # Ensure primary key exists in obj_dict
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
        """
        Save an object to Cassandra database.
        Similar to MongoDB's save_to_mongodb method.
        """
        # Determine table name based on object type
        if isinstance(obj, dict):
            table_name = "dictionary"
        elif hasattr(obj, "__class__"):
            table_name = obj.__class__.__name__.lower()
        else:
            table_name = type(obj).__name__.lower()

        cassandra_obj = {}

        # Extract fields from object
        if hasattr(obj, "__dict__"):
            for attr, value in vars(obj).items():
                cassandra_obj[attr] = self.convert_to_cassandra_type(value)
        else:
            # Handle non-class objects
            cassandra_obj = {"value": self.convert_to_cassandra_type(obj)}

        # Set id if provided or generate a new one
        if document_id is not None:
            cassandra_obj["id"] = document_id
        elif "id" not in cassandra_obj:
            cassandra_obj["id"] = uuid.uuid4()

        # Add type information
        cassandra_obj["_type"] = type(obj).__name__

        # Create or update table
        if not self._table_exists(table_name):
            self._create_table_from_dict(table_name, cassandra_obj, primary_key="id")
            primary_key = "id"
        else:
            primary_key = self._get_primary_key(table_name)
            # Ensure primary key exists
            if primary_key not in cassandra_obj:
                cassandra_obj[primary_key] = uuid.uuid4()

            self._ensure_table_columns(table_name, cassandra_obj)

        # Prepare and execute insert query
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
        """
        Retrieve objects from Cassandra database.
        Similar to MongoDB's retrieve_from_mongodb method.

        Note: Cassandra doesn't support complex queries like MongoDB.
        The query parameter is simplified to handle basic equality conditions.
        """
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
        """Close the database connection"""
        self.cluster.shutdown()


# Example usage
if __name__ == "__main__":
    from example_objects import objects_list

    converter = PyCassandraConverter(keyspace="object_db")

    try:
        for obj in objects_list:
            converter.save_to_cassandra(obj)

    finally:
        converter.close()