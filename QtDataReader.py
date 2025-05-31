import sys
import json  # For MongoDB query parsing
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QLineEdit, QFormLayout, QScrollArea, QTabWidget,
    QTextEdit, QGroupBox
)
from PyQt6.QtCore import Qt
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from typing import Dict, List, Optional, Any, Tuple
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError, CypherSyntaxError
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement, PreparedStatement
from cassandra import InvalidRequest


# --- DB Handlers: Connections ---
class MongoConnection:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.client = None

    def connect(self):
        try:
            self.client = MongoClient(self.connection_string, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            return True, "Connected successfully"
        except ConnectionFailure as e:
            self.client = None
            return False, f"MongoDB Connection Failure: {str(e)}"
        except Exception as e:
            self.client = None
            return False, f"MongoDB Error: {str(e)}"

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def get_client(self):
        return self.client


class Neo4jConnection:
    def __init__(self, uri, username, password):
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None

    def connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            with self.driver.session(database="neo4j") as session:
                session.run("RETURN 1 AS test").single()
            return True, "Connected successfully"
        except (ServiceUnavailable, AuthError) as e:
            self.driver = None
            return False, f"Neo4j Connection/Auth Error: {str(e)}"
        except Exception as e:
            self.driver = None
            return False, f"Neo4j Error: {str(e)}"

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None

    def get_driver(self):
        return self.driver


class CassandraConnection:
    def __init__(self, contact_points, username=None, password=None):
        self.contact_points = contact_points
        self.username = username
        self.password = password
        self.cluster = None
        self.session = None

    def connect(self):
        auth_provider = None
        if self.username:
            auth_provider = PlainTextAuthProvider(username=self.username, password=self.password)
        try:
            self.cluster = Cluster(contact_points=self.contact_points,
                                   auth_provider=auth_provider,
                                   connect_timeout=10)
            self.session = self.cluster.connect()
            return True, "Connected successfully"
        except NoHostAvailable as e:
            self.cluster = None
            self.session = None
            return False, f"Cassandra NoHostAvailable: {str(e)}"
        except Exception as e:
            self.cluster = None
            self.session = None
            return False, f"Cassandra Error: {str(e)}"

    def close(self):
        if self.session:
            self.session.shutdown()
            self.session = None
        if self.cluster:
            self.cluster.shutdown()
            self.cluster = None

    def get_session(self):
        return self.session

    def get_cluster_metadata(self):
        return self.cluster.metadata if self.cluster else None


# --- DB Handlers: Metadata Fetchers ---
class MongoMetadataFetcher:
    def __init__(self, mongo_connection: MongoConnection):
        self.conn = mongo_connection

    def list_databases(self) -> List[str]:
        client = self.conn.get_client()
        if not client: return []
        try:
            return sorted([db for db in client.list_database_names() if db not in ['admin', 'config', 'local']])
        except Exception:
            return []

    def list_collections(self, db_name: str) -> List[str]:
        client = self.conn.get_client()
        if not client or not db_name: return []
        try:
            db = client[db_name]
            return sorted(db.list_collection_names())
        except Exception:
            return []

    def get_collection_fields(self, db_name: str, collection_name: str) -> List[str]:
        client = self.conn.get_client()
        if not client or not db_name or not collection_name: return []
        try:
            db = client[db_name]
            collection = db[collection_name]
            doc = collection.find_one()
            return sorted([k for k in doc.keys() if k != "_id"]) if doc else []
        except Exception:
            return []


class Neo4jMetadataFetcher:
    def __init__(self, neo4j_connection: Neo4jConnection):
        self.conn = neo4j_connection

    def list_labels(self) -> List[str]:
        driver = self.conn.get_driver()
        if not driver: return []
        try:
            with driver.session(database="neo4j") as session:
                result = session.run("CALL db.labels() YIELD label RETURN label")
                return sorted([record["label"] for record in result])
        except Exception:
            try:
                with driver.session(database="neo4j") as session:
                    result = session.run("CALL db.labels()")  # Fallback for older versions
                    return sorted([record["label"] for record in result])
            except Exception:
                return []

    def get_label_properties(self, label_name: str) -> List[str]:
        driver = self.conn.get_driver()
        if not driver or not label_name: return []
        try:
            # Sanitize label_name slightly for query
            safe_label_name = label_name.replace('`', '``')
            query = f"MATCH (n:`{safe_label_name}`) WITH n LIMIT 100 UNWIND keys(n) AS prop RETURN DISTINCT prop ORDER BY prop"
            with driver.session(database="neo4j") as session:
                result = session.run(query)
                return [record["prop"] for record in result]
        except Exception:
            return []


class CassandraMetadataFetcher:
    def __init__(self, cassandra_connection: CassandraConnection):
        self.conn = cassandra_connection

    def list_keyspaces(self) -> List[str]:
        metadata = self.conn.get_cluster_metadata()
        if not metadata: return []
        try:
            keyspace_names = list(metadata.keyspaces.keys())
            system_keyspaces = {'system', 'system_auth', 'system_distributed', 'system_schema',
                                'system_traces', 'system_views', 'system_virtual_schema',
                                'dse_system', 'dse_auth', 'dse_perf', 'dse_insights', 'dse_insights_local',
                                'solr_admin'}
            return sorted([ks for ks in keyspace_names if
                           ks not in system_keyspaces and not ks.startswith("dse_") and not ks.startswith("solr_")])
        except Exception:
            return []

    def list_tables(self, keyspace_name: str) -> List[str]:
        metadata = self.conn.get_cluster_metadata()
        if not metadata or not keyspace_name: return []
        try:
            keyspace_meta = metadata.keyspaces.get(keyspace_name)
            return sorted(list(keyspace_meta.tables.keys())) if keyspace_meta else []
        except Exception:
            return []

    def get_table_columns(self, keyspace_name: str, table_name: str) -> List[str]:
        metadata = self.conn.get_cluster_metadata()
        if not metadata or not keyspace_name or not table_name: return []
        try:
            table_meta = metadata.keyspaces[keyspace_name].tables.get(table_name)
            return sorted(list(table_meta.columns.keys())) if table_meta else []
        except Exception:
            return []

    def get_column_cql_type(self, keyspace_name: str, table_name: str, column_name: str) -> Optional[str]:
        metadata = self.conn.get_cluster_metadata()
        if not metadata: return None
        try:
            return metadata.keyspaces[keyspace_name].tables[table_name].columns[column_name].cql_type
        except (KeyError, AttributeError):
            return None


# --- DB Handlers: Query Handlers / Search Services ---
def attempt_type_conversion(value_str: str) -> Any:
    if value_str.lower() == "true": return True
    if value_str.lower() == "false": return False
    try:
        return int(value_str)
    except ValueError:
        try:
            return float(value_str)
        except ValueError:
            return value_str


class MongoSearchService:
    def __init__(self, mongo_connection: MongoConnection):
        self.conn = mongo_connection

    def _build_query(self, field: str, operator: str, value: Any) -> Dict:
        query = {}
        if "równa się" in operator:
            query[field] = value
        elif "nie równa się" in operator:
            query[field] = {"$ne": value}
        elif "większe niż" in operator:
            query[field] = {"$gt": value}
        elif "większe lub równe" in operator:
            query[field] = {"$gte": value}
        elif "mniejsze niż" in operator:
            query[field] = {"$lt": value}
        elif "mniejsze lub równe" in operator:
            query[field] = {"$lte": value}
        elif "zawiera" in operator:
            query[field] = {"$regex": value, "$options": "i"} if isinstance(value, str) else value
        elif "zaczyna się od" in operator:
            query[field] = {"$regex": f"^{value}", "$options": "i"} if isinstance(value, str) else {}
        elif "kończy się na" in operator:
            query[field] = {"$regex": f"{value}$", "$options": "i"} if isinstance(value, str) else {}
        return query

    def search(self, db_name: str, collection_name: str, field: str, operator: str, value_str: str) -> Tuple[
        List[Dict], int, Optional[str]]:
        client = self.conn.get_client()
        if not client or not db_name or not collection_name:
            return [], 0, "Not connected or database/collection not selected."
        try:
            db = client[db_name]
            collection = db[collection_name]
            query_value = attempt_type_conversion(value_str)
            query = self._build_query(field, operator, query_value)
            results = list(collection.find(query).limit(100))
            # For count, use the same query. Consider estimated_document_count for large collections if exact count isn't critical.
            count = collection.count_documents(query)
            return results, count, None
        except Exception as e:
            return [], 0, f"MongoDB Search Error: {str(e)}"

    def execute_raw_query(self, db_name: str, collection_name: str, query_str: str, limit: int = 50) -> Tuple[
        List[Dict], int, Optional[str]]:
        client = self.conn.get_client()
        if not client or not db_name or not collection_name:
            return [], 0, "Not connected or database/collection not selected."
        try:
            db = client[db_name]
            collection = db[collection_name]

            parsed_query = {}
            if query_str.strip():  # If query is not empty
                try:
                    # MongoDB find queries are Python dicts, so use json.loads carefully or ast.literal_eval
                    # For simplicity, assuming query_str is a valid JSON parsable to a dict
                    parsed_query = json.loads(query_str)
                    if not isinstance(parsed_query, dict):
                        return [], 0, "Invalid query format: Query must be a JSON object string."
                except json.JSONDecodeError as je:
                    return [], 0, f"Invalid query format: Not a valid JSON. Error: {str(je)}"

            # If query is empty, it means find all, which is {}
            results = list(collection.find(parsed_query).limit(limit))
            # Count can be based on the same query.
            # For an empty query string (parsed_query = {}), this counts all documents.
            count = collection.count_documents(parsed_query)
            return results, count, None
        except OperationFailure as oe:  # More specific MongoDB errors
            return [], 0, f"MongoDB Operation Failure: {str(oe)}"
        except Exception as e:
            return [], 0, f"MongoDB Raw Query Error: {str(e)}"


class Neo4jSearchService:
    def __init__(self, neo4j_connection: Neo4jConnection):
        self.conn = neo4j_connection

    def _build_query(self, label: str, field: str, operator: str, value: Any) -> Tuple[str, Dict]:
        params = {"value": value}
        safe_label = label.replace('`', '``')  # Basic sanitization

        if "istnieje relacja z" in operator:
            rel_type_str = str(value).strip().replace('`', '')
            q = f"MATCH (n:`{safe_label}`)-[r{':`' + rel_type_str + '`' if rel_type_str else ''}]->(m) RETURN n, r, m LIMIT 100"
            return q, {}

        if not field:
            return f"MATCH (n:`{safe_label}`) RETURN n LIMIT 100", {}

        backtick_char = '`'
        double_backtick_char = '``'
        escaped_field_content = field.replace(backtick_char, double_backtick_char)
        safe_field = backtick_char + escaped_field_content + backtick_char

        q_match = f"MATCH (n:`{safe_label}`) "
        q_where = ""
        op_map = {
            "równa się (=)": f"n.{safe_field} = $value",
            "nie równa się (!=)": f"NOT n.{safe_field} = $value",
            "większe niż (>)": f"n.{safe_field} > $value",
            "większe lub równe (>=)": f"n.{safe_field} >= $value",
            "mniejsze niż (<)": f"n.{safe_field} < $value",
            "mniejsze lub równe (<=)": f"n.{safe_field} <= $value",
        }
        if operator in op_map:
            q_where = op_map[operator]
        elif "zawiera" in operator:
            q_where = f"toLower(toString(n.{safe_field})) CONTAINS toLower($value)" if isinstance(value,
                                                                                                  str) else f"n.{safe_field} CONTAINS $value"
        elif "zaczyna się od" in operator:
            q_where = f"toLower(toString(n.{safe_field})) STARTS WITH toLower($value)" if isinstance(value, str) else ""
        elif "kończy się na" in operator:
            q_where = f"toLower(toString(n.{safe_field})) ENDS WITH toLower($value)" if isinstance(value, str) else ""

        full_q = q_match
        if q_where: full_q += "WHERE " + q_where
        full_q += " RETURN n LIMIT 100"
        return full_q, params

    def search(self, label: str, field: str, operator: str, value_str: str) -> Tuple[
        Dict[str, List], int, Optional[str]]:
        driver = self.conn.get_driver()
        if not driver:
            return {"nodes": [], "relationships": [], "paths": [], "raw_records": []}, 0, "Not connected."

        query_str = ""
        try:
            query_value = attempt_type_conversion(value_str)
            query_str, params = self._build_query(label, field, operator, query_value)

            neo4j_results = {"nodes": [], "relationships": [], "paths": [], "raw_records": []}
            count = 0
            with driver.session(database="neo4j") as session:
                result_cursor = session.run(query_str, parameters=params)
                record_list = list(result_cursor)
                count = len(record_list)  # This is count of returned limited records
                for record in record_list:
                    processed_record = False
                    for key_rec in record.keys():
                        val = record[key_rec]
                        if hasattr(val, 'labels') and hasattr(val, 'element_id'):
                            if val not in neo4j_results["nodes"]: neo4j_results["nodes"].append(val)
                            processed_record = True
                        elif hasattr(val, 'type') and hasattr(val, 'start_node') and hasattr(val, 'end_node'):
                            if val not in neo4j_results["relationships"]: neo4j_results["relationships"].append(val)
                            processed_record = True
                        elif hasattr(val, 'start_node') and hasattr(val, 'nodes') and hasattr(val, 'relationships'):
                            if val not in neo4j_results["paths"]: neo4j_results["paths"].append(val)
                            processed_record = True
                    if not processed_record and record not in neo4j_results["raw_records"]:
                        neo4j_results["raw_records"].append(record)
            return neo4j_results, count, None
        except Exception as e:
            return {"nodes": [], "relationships": [], "paths": [],
                    "raw_records": []}, 0, f"Neo4j Search Error: {str(e)}\nQuery: {query_str}"

    def execute_raw_cypher(self, cypher_query: str) -> Tuple[List[Dict], Optional[str]]:
        driver = self.conn.get_driver()
        if not driver:
            return [], "Not connected to Neo4j."
        try:
            with driver.session(database="neo4j") as session:
                result_cursor = session.run(cypher_query)
                # Convert records to a list of dictionaries for easier display
                records_as_dicts = [record.data() for record in result_cursor]
                return records_as_dicts, None
        except CypherSyntaxError as cse:
            return [], f"Neo4j Cypher Syntax Error: {str(cse)}"
        except Exception as e:
            return [], f"Neo4j Raw Query Error: {str(e)}"


class CassandraSearchService:
    def __init__(self, cassandra_connection: CassandraConnection, metadata_fetcher: CassandraMetadataFetcher):
        self.conn = cassandra_connection
        self.meta_fetcher = metadata_fetcher

    def _attempt_type_conversion_for_cassandra(self, value_str: str, keyspace: str, table: str,
                                               column_name: str) -> Any:
        col_type_name = self.meta_fetcher.get_column_cql_type(keyspace, table, column_name)
        if col_type_name:
            try:
                if col_type_name in ['int', 'bigint', 'smallint', 'tinyint', 'varint', 'counter']:
                    return int(value_str)
                elif col_type_name in ['float', 'double', 'decimal']:
                    return float(value_str)
                elif col_type_name == 'boolean':
                    return value_str.lower() == 'true'
            except ValueError:
                pass
        return attempt_type_conversion(value_str)

    def _build_query(self, keyspace: str, table: str, field: str, operator: str, value: Any) -> Tuple[str, Dict]:
        safe_keyspace = '"' + keyspace.replace('"', '""') + '"'
        safe_table = '"' + table.replace('"', '""') + '"'
        safe_field = '"' + field.replace('"', '""') + '"'

        cql_value_str = ""
        if isinstance(value, str):
            escaped_user_value = value.replace("'", "''")
            if operator == "zawiera":
                cql_value_str = f"'%{escaped_user_value}%'"
            elif operator == "zaczyna się od":
                cql_value_str = f"'{escaped_user_value}%'"
            elif operator == "kończy się na":
                cql_value_str = f"'%{escaped_user_value}'"
            else:
                cql_value_str = f"'{escaped_user_value}'"
        elif isinstance(value, bool):
            cql_value_str = str(value).lower()
        else:
            cql_value_str = str(value)

        query_string = f"SELECT * FROM {safe_keyspace}.{safe_table} "
        condition = ""
        if operator == "równa się (=)":
            condition = f"{safe_field} = {cql_value_str}"
        elif operator == "nie równa się (!=)":
            condition = f"{safe_field} != {cql_value_str}"
        elif operator == "większe niż (>)":
            condition = f"{safe_field} > {cql_value_str}"
        elif operator == "większe lub równe (>=)":
            condition = f"{safe_field} >= {cql_value_str}"
        elif operator == "mniejsze niż (<)":
            condition = f"{safe_field} < {cql_value_str}"
        elif operator == "mniejsze lub równe (<=)":
            condition = f"{safe_field} <= {cql_value_str}"
        elif operator in ["zawiera", "zaczyna się od", "kończy się na"]:
            condition = f"{safe_field} LIKE {cql_value_str}"

        if condition: query_string += f"WHERE {condition} "
        query_string += "LIMIT 100"

        if "WHERE" in query_string:
            is_pk_component = False
            metadata = self.conn.get_cluster_metadata()
            if metadata:
                try:
                    table_meta = metadata.keyspaces[keyspace].tables[table]
                    pk_components = [col.name for col in table_meta.primary_key]
                    if field in pk_components: is_pk_component = True
                except (KeyError, AttributeError):
                    pass
            if not is_pk_component and "ALLOW FILTERING" not in query_string:
                query_string += " ALLOW FILTERING"
        return query_string, {}

    def search(self, keyspace: str, table: str, field: str, operator: str, value_str: str) -> Tuple[
        List[Any], int, Optional[str]]:
        session = self.conn.get_session()
        if not session or not keyspace or not table:
            return [], 0, "Not connected or keyspace/table not selected."

        query_string = ""
        try:
            query_value = self._attempt_type_conversion_for_cassandra(value_str, keyspace, table, field)
            query_string, _ = self._build_query(keyspace, table, field, operator, query_value)
            statement = SimpleStatement(query_string, fetch_size=100)
            rows = list(session.execute(statement))
            count = len(rows)  # SimpleStatement with LIMIT returns at most that many records
            return rows, count, None
        except InvalidRequest as e:
            return [], 0, f"Cassandra Invalid Request: {str(e)}\nQuery: {query_string}"
        except Exception as e:
            return [], 0, f"Cassandra Search Error: {str(e)}\nQuery: {query_string}"

    def execute_raw_cql(self, cql_query: str) -> Tuple[List[Any], Optional[str]]:
        session = self.conn.get_session()
        if not session:
            return [], "Not connected to Cassandra."
        try:
            statement = SimpleStatement(cql_query, fetch_size=100)  # Add fetch_size for potentially large results
            rows = list(session.execute(statement))
            return rows, None
        except InvalidRequest as ir:
            return [], f"Cassandra Invalid CQL Request: {str(ir)}"
        except Exception as e:
            return [], f"Cassandra Raw Query Error: {str(e)}"


# --- UI Helpers: Result Display Manager ---
class ResultDisplayManager:
    def __init__(self, tree_widget: QTreeWidget):
        self.tree_widget = tree_widget

    def clear_results(self, default_headers: List[str] = ["Pole", "Wartość"]):
        self.tree_widget.clear()
        self.tree_widget.setHeaderLabels(default_headers)
        self.tree_widget.setColumnCount(len(default_headers))

    def _add_data_to_node(self, data_item: Any, parent_tree_item: QTreeWidgetItem, db_type_hint: str):
        if isinstance(data_item, dict):
            for key, value in data_item.items():
                if db_type_hint == "mongodb" and key == "_id" and parent_tree_item.text(0).startswith("Dokument:"):
                    continue
                child_node_text = str(key)
                if isinstance(value, dict):
                    child_item = QTreeWidgetItem([child_node_text])
                    self._add_data_to_node(value, child_item, db_type_hint)
                    parent_tree_item.addChild(child_item)
                    child_item.setExpanded(True)
                elif isinstance(value, list):
                    child_item = QTreeWidgetItem([child_node_text, f"(lista: {len(value)} el.)"])
                    parent_tree_item.addChild(child_item)
                    for i, list_el in enumerate(value):
                        list_el_item = QTreeWidgetItem([f"[{i}]"])
                        self._add_data_to_node(list_el, list_el_item, db_type_hint)
                        child_item.addChild(list_el_item)
                    child_item.setExpanded(True)
                else:
                    child_value_text = str(value)
                    item = QTreeWidgetItem([child_node_text, child_value_text])
                    parent_tree_item.addChild(item)
        elif isinstance(data_item, list):
            parent_tree_item.setText(0, parent_tree_item.text(0) + f" (lista: {len(data_item)} el.)")
            for i, list_el in enumerate(data_item):
                list_el_item = QTreeWidgetItem([f"[{i}]"])
                self._add_data_to_node(list_el, list_el_item, db_type_hint)
                parent_tree_item.addChild(list_el_item)
            parent_tree_item.setExpanded(True)
        elif db_type_hint == "neo4j" and not isinstance(data_item, (dict, list)):
            # Special handling for Neo4jTab's general query executor display
            if parent_tree_item.columnCount() > 1 and parent_tree_item.text(1) == "":
                parent_tree_item.setText(1, str(data_item))
            elif parent_tree_item.columnCount() == 1 and parent_tree_item.text(0) == "":  # If item text itself is empty
                parent_tree_item.setText(0, str(data_item))
            elif parent_tree_item.columnCount() == 1:  # Append to existing text
                current_text = parent_tree_item.text(0)
                if current_text and not current_text.endswith(": "):
                    parent_tree_item.setText(0, f"{current_text}: {str(data_item)}")
                else:
                    parent_tree_item.setText(0, f"{current_text}{str(data_item)}")


        elif not isinstance(data_item, (dict, list)) and parent_tree_item.columnCount() > 1 and parent_tree_item.text(
                1) == "":
            parent_tree_item.setText(1, str(data_item))

    def display_mongodb_results(self, results: List[Dict], count: int, is_raw_query: bool = False) -> str:
        self.clear_results(["Pole", "Wartość"])
        if is_raw_query:  # For raw queries, each result is a document
            for i, doc in enumerate(results):
                doc_item = QTreeWidgetItem([f"Dokument {i + 1}"])  # Generic ID for raw query results
                self._add_data_to_node(doc, doc_item, "mongodb")
                self.tree_widget.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)
        else:  # For structured search
            for i, doc in enumerate(results):
                doc_id = doc.get('_id', f'Dokument {i + 1}')
                doc_item = QTreeWidgetItem([f"Dokument: {doc_id}"])
                self._add_data_to_node(doc, doc_item, "mongodb")
                self.tree_widget.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)

        # Count can be total documents matching (from service) or just displayed (len(results))
        # Using the count from the service is more informative for the user about the query's scope
        return f"Znaleziono dokumentów: {count} (wyświetlono: {len(results)})"

    def display_neo4j_results(self, results_data: Dict[str, List], count: int) -> str:  # For SearchTab
        self.clear_results(["Typ", "Właściwości/Szczegóły"])
        # ... (existing SearchTab Neo4j display logic)
        if results_data.get("nodes"):
            parent = QTreeWidgetItem(["Węzły", f"{len(results_data['nodes'])} znaleziono"]);
            self.tree_widget.addTopLevelItem(parent)
            for node in results_data['nodes']:
                labels_str = ", ".join(node.labels) if node.labels else "Brak etykiet"
                item = QTreeWidgetItem([f"Węzeł ({labels_str})", f"id: {node.element_id}"])
                self._add_data_to_node(dict(node.items()), item, "neo4j");
                parent.addChild(item)
            parent.setExpanded(True)
        if results_data.get("relationships"):
            parent = QTreeWidgetItem(["Relacje", f"{len(results_data['relationships'])} znaleziono"]);
            self.tree_widget.addTopLevelItem(parent)
            for rel in results_data['relationships']:
                item = QTreeWidgetItem([f"Relacja ({rel.type})", f"id: {rel.element_id}"])
                item.addChild(
                    QTreeWidgetItem(["Od", f"({', '.join(rel.start_node.labels)}) id: {rel.start_node.element_id}"]))
                item.addChild(
                    QTreeWidgetItem(["Do", f"({', '.join(rel.end_node.labels)}) id: {rel.end_node.element_id}"]))
                self._add_data_to_node(dict(rel.items()), item, "neo4j");
                parent.addChild(item)
            parent.setExpanded(True)
        if results_data.get("paths"):
            parent = QTreeWidgetItem(["Ścieżki", f"{len(results_data['paths'])} znaleziono"]);
            self.tree_widget.addTopLevelItem(parent)
            for i, path_val in enumerate(results_data['paths']):
                item = QTreeWidgetItem([f"Ścieżka {i + 1}", f"Długość: {len(path_val.relationships)}"]);
                parent.addChild(item)
            parent.setExpanded(True)
        if results_data.get("raw_records"):
            parent = QTreeWidgetItem(["Inne Wyniki", f"{len(results_data['raw_records'])} rekordów"]);
            self.tree_widget.addTopLevelItem(parent)
            for i, record_val in enumerate(results_data['raw_records']):
                item = QTreeWidgetItem([f"Rekord {i + 1}"])
                self._add_data_to_node(dict(record_val.items()), item, "neo4j");
                parent.addChild(item)
            parent.setExpanded(True)
        return f"Znaleziono wyników: {count}"  # Count here is num of items returned by the specific search query

    def display_neo4j_raw_query_results(self, records: List[Dict]) -> str:  # For Neo4jTab
        self.clear_results()  # Headers will be set from data
        if not records:
            self.tree_widget.setHeaderLabels(["Wynik"])
            self.tree_widget.addTopLevelItem(QTreeWidgetItem(["Zapytanie wykonane, brak rekordów."]))
            return "Wyniki: 0"

        # Set headers from the keys of the first record
        if records[0]:
            self.tree_widget.setHeaderLabels(list(records[0].keys()))
            self.tree_widget.setColumnCount(len(records[0].keys()))
        else:  # Should not happen if records is not empty, but as a fallback
            self.tree_widget.setHeaderLabels(["Pusty Rekord"])
            self.tree_widget.setColumnCount(1)

        for i, record_dict in enumerate(records):
            if len(record_dict.keys()) == 1:  # Single column result
                key = list(record_dict.keys())[0]
                # Create a top-level item representing the row, then add the value
                # This requires _add_data_to_node to handle cases where parent_item is for the row
                # and the value should go into its column(s) or as children if complex.
                row_item_text = str(record_dict[key]) if not isinstance(record_dict[key], (dict,
                                                                                           list)) else f"Rekord {i + 1} (Szczegóły poniżej)"
                item = QTreeWidgetItem([row_item_text])
                if isinstance(record_dict[key], (dict, list)):  # If complex, add as children
                    self._add_data_to_node(record_dict[key], item, "neo4j")
                    item.setExpanded(True)

            else:  # Multiple columns
                # Use the first column's value as the item text, or a generic "Record X"
                # For simplicity, using "Record X" and then child items for each field.
                item = QTreeWidgetItem([f"Rekord {i + 1}"])
                for key, value in record_dict.items():
                    child_item = QTreeWidgetItem([str(key)])  # Key in first col
                    self._add_data_to_node(value, child_item, "neo4j")  # Value in second col or as children
                    item.addChild(child_item)
                item.setExpanded(True)
            self.tree_widget.addTopLevelItem(item)

        for col_idx in range(self.tree_widget.columnCount()):
            self.tree_widget.resizeColumnToContents(col_idx)
        return f"Wyniki: {len(records)}"

    def display_cassandra_results(self, results: List[Any], count: int, is_raw_query: bool = False) -> str:
        self.clear_results()
        if results and isinstance(results, list) and len(results) > 0 and hasattr(results[0], '_fields'):
            column_names = list(results[0]._fields)
            self.tree_widget.setColumnCount(len(column_names))
            self.tree_widget.setHeaderLabels(column_names)
            for row_data in results:
                row_values = [str(getattr(row_data, col, 'N/A')) for col in column_names]
                self.tree_widget.addTopLevelItem(QTreeWidgetItem(row_values))
            for i in range(len(column_names)): self.tree_widget.resizeColumnToContents(i)
        elif results:
            self.tree_widget.setHeaderLabels(["Wynik Cassandra"]);
            self.tree_widget.setColumnCount(1)
            self.tree_widget.addTopLevelItem(QTreeWidgetItem([str(results)]))
        else:
            self.tree_widget.setHeaderLabels(["Wyniki Cassandra"]);
            self.tree_widget.setColumnCount(1)
            self.tree_widget.addTopLevelItem(QTreeWidgetItem(["Brak wyników"]))

        # For Cassandra, count usually means rows returned by the (LIMITed) query.
        return f"Zwrócono wierszy: {len(results)}"


# --- UI Tabs ---
class SearchTab(QWidget):
    # ... (SearchTab remains largely the same as in the previous "all in one file" example)
    def __init__(self):
        super().__init__()
        # Connections
        self.mongo_conn: Optional[MongoConnection] = None
        self.neo4j_conn: Optional[Neo4jConnection] = None
        self.cassandra_conn: Optional[CassandraConnection] = None

        # Metadata Fetchers
        self.mongo_meta_fetcher: Optional[MongoMetadataFetcher] = None
        self.neo4j_meta_fetcher: Optional[Neo4jMetadataFetcher] = None
        self.cassandra_meta_fetcher: Optional[CassandraMetadataFetcher] = None

        # Search Services
        self.mongo_search_service: Optional[MongoSearchService] = None
        self.neo4j_search_service: Optional[Neo4jSearchService] = None
        self.cassandra_search_service: Optional[CassandraSearchService] = None

        self.current_db_name = ""
        self.current_entity_name = ""
        self.current_db_type = "mongodb"

        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.results_tree)
        self._set_db_type_mongodb_ui_elements()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        db_type_group = QGroupBox("Typ bazy danych")
        db_type_layout = QHBoxLayout(db_type_group)
        self.mongodb_rb = QPushButton("MongoDB");
        self.mongodb_rb.setCheckable(True);
        self.mongodb_rb.setChecked(True)
        self.neo4j_rb = QPushButton("Neo4j");
        self.neo4j_rb.setCheckable(True)
        self.cassandra_rb = QPushButton("Cassandra");
        self.cassandra_rb.setCheckable(True)
        self.mongodb_rb.clicked.connect(self._set_db_type_mongodb)
        self.neo4j_rb.clicked.connect(self._set_db_type_neo4j)
        self.cassandra_rb.clicked.connect(self._set_db_type_cassandra)
        db_type_layout.addWidget(self.mongodb_rb);
        db_type_layout.addWidget(self.neo4j_rb);
        db_type_layout.addWidget(self.cassandra_rb)
        main_layout.addWidget(db_type_group)

        self.connection_group = QGroupBox("Połączenie z bazą danych")
        connection_layout = QFormLayout(self.connection_group)
        self.connection_input_label_widget = QLabel("Connection String:")
        self.connection_input = QLineEdit("mongodb://localhost:27017/")
        connection_layout.addRow(self.connection_input_label_widget, self.connection_input)
        self.neo4j_user_label = QLabel("Neo4j Username:");
        self.neo4j_user_input = QLineEdit("neo4j")
        self.neo4j_pass_label = QLabel("Neo4j Password:");
        self.neo4j_pass_input = QLineEdit();
        self.neo4j_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow(self.neo4j_user_label, self.neo4j_user_input)
        connection_layout.addRow(self.neo4j_pass_label, self.neo4j_pass_input)
        self.cassandra_user_label_search = QLabel("Cassandra Username:");
        self.cassandra_user_input_search = QLineEdit();
        self.cassandra_user_input_search.setPlaceholderText("(Optional)")
        self.cassandra_pass_label_search = QLabel("Cassandra Password:");
        self.cassandra_pass_input_search = QLineEdit();
        self.cassandra_pass_input_search.setPlaceholderText("(Optional)");
        self.cassandra_pass_input_search.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow(self.cassandra_user_label_search, self.cassandra_user_input_search)
        connection_layout.addRow(self.cassandra_pass_label_search, self.cassandra_pass_input_search)
        self.connect_btn = QPushButton("Połącz");
        self.connect_btn.clicked.connect(self._connect_to_db)
        connection_layout.addRow(self.connect_btn)
        self.connection_status_label_widget = QLabel("Status:")
        self.connection_status = QLabel("Niepołączono");
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow(self.connection_status_label_widget, self.connection_status)
        main_layout.addWidget(self.connection_group)

        self.selection_group = QGroupBox("Wybór danych")
        selection_layout = QFormLayout(self.selection_group)
        self.db_combo_label = QLabel("Baza danych:");
        self.db_combo = QComboBox()
        self.db_combo.currentTextChanged.connect(self._update_entities_combo)
        self.entity_combo_label = QLabel("Kolekcja/Tabela:");
        self.entity_combo = QComboBox()
        self.entity_combo.currentTextChanged.connect(self._update_search_fields)
        selection_layout.addRow(self.db_combo_label, self.db_combo)
        selection_layout.addRow(self.entity_combo_label, self.entity_combo)
        main_layout.addWidget(self.selection_group)

        search_group = QGroupBox("Kryteria wyszukiwania")
        search_layout = QFormLayout(search_group)
        self.field_combo = QComboBox();
        search_layout.addRow("Pole:", self.field_combo)
        self.operator_combo = QComboBox();
        self._update_operators();
        search_layout.addRow("Operator:", self.operator_combo)
        self.value_input = QLineEdit();
        search_layout.addRow("Wartość:", self.value_input)
        self.search_btn = QPushButton("Wyszukaj");
        self.search_btn.clicked.connect(self._perform_search);
        self.search_btn.setEnabled(False)
        search_layout.addRow(self.search_btn)
        self.clear_btn = QPushButton("Wyczyść");
        self.clear_btn.clicked.connect(self._clear_search_ui_and_results);
        self.clear_btn.setEnabled(False)
        search_layout.addRow(self.clear_btn)
        main_layout.addWidget(search_group)

        results_group = QGroupBox("Wyniki wyszukiwania")
        results_layout = QVBoxLayout(results_group)
        self.results_tree = QTreeWidget();
        self.results_tree.setHeaderLabels(["Pole", "Wartość"]);
        self.results_tree.setColumnWidth(0, 300)
        self.results_count = QLabel("Znaleziono wyników: 0")
        results_layout.addWidget(self.results_tree);
        results_layout.addWidget(self.results_count)
        main_layout.addWidget(results_group)

        self._set_db_specific_connection_fields_visibility("mongodb")

    def _set_db_specific_connection_fields_visibility(self, db_type: str):
        is_mongo = db_type == "mongodb";
        is_neo4j = db_type == "neo4j";
        is_cassandra = db_type == "cassandra"
        self.neo4j_user_label.setVisible(is_neo4j);
        self.neo4j_user_input.setVisible(is_neo4j)
        self.neo4j_pass_label.setVisible(is_neo4j);
        self.neo4j_pass_input.setVisible(is_neo4j)
        self.cassandra_user_label_search.setVisible(is_cassandra);
        self.cassandra_user_input_search.setVisible(is_cassandra)
        self.cassandra_pass_label_search.setVisible(is_cassandra);
        self.cassandra_pass_input_search.setVisible(is_cassandra)

    def _set_db_type_mongodb_ui_elements(self):
        self.connection_input.setText("mongodb://localhost:27017/");
        self.connection_input_label_widget.setText("Connection String:")
        self._set_db_specific_connection_fields_visibility("mongodb")
        self.selection_group.setTitle("Wybór bazy danych i kolekcji MongoDB");
        self.db_combo_label.setText("Baza danych:");
        self.entity_combo_label.setText("Kolekcja:")

    def _set_db_type_neo4j_ui_elements(self):
        self.connection_input.setText("bolt://localhost:7687");
        self.neo4j_user_input.setText("neo4j");
        self.neo4j_pass_input.clear()
        self.connection_input_label_widget.setText("URI:");
        self._set_db_specific_connection_fields_visibility("neo4j")
        self.selection_group.setTitle("Wybór danych Neo4j");
        self.db_combo_label.setText("Baza danych:");
        self.entity_combo_label.setText("Etykieta:")

    def _set_db_type_cassandra_ui_elements(self):
        self.connection_input.setText("127.0.0.1");
        self.cassandra_user_input_search.clear();
        self.cassandra_pass_input_search.clear()
        self.connection_input_label_widget.setText("Contact Points:");
        self._set_db_specific_connection_fields_visibility("cassandra")
        self.selection_group.setTitle("Wybór danych Cassandra");
        self.db_combo_label.setText("Keyspace:");
        self.entity_combo_label.setText("Tabela:")

    def _update_button_group(self, active_button_name: str):
        buttons = {"mongodb": self.mongodb_rb, "neo4j": self.neo4j_rb, "cassandra": self.cassandra_rb}
        for name, button in buttons.items():
            button.setChecked(name == active_button_name)

    def _set_db_type_mongodb(self):
        if self.current_db_type == "mongodb" and self.mongodb_rb.isChecked(): return
        self.current_db_type = "mongodb"
        self._update_button_group("mongodb")
        self._set_db_type_mongodb_ui_elements()
        self._update_operators()
        if self.mongo_conn and self.mongo_conn.get_client():
            if not self.mongo_meta_fetcher: self.mongo_meta_fetcher = MongoMetadataFetcher(self.mongo_conn)
            if not self.mongo_search_service: self.mongo_search_service = MongoSearchService(self.mongo_conn)
        self._update_ui_for_current_connection()

    def _set_db_type_neo4j(self):
        if self.current_db_type == "neo4j" and self.neo4j_rb.isChecked(): return
        self.current_db_type = "neo4j"
        self._update_button_group("neo4j")
        self._set_db_type_neo4j_ui_elements()
        self._update_operators()
        if self.neo4j_conn and self.neo4j_conn.get_driver():
            if not self.neo4j_meta_fetcher: self.neo4j_meta_fetcher = Neo4jMetadataFetcher(self.neo4j_conn)
            if not self.neo4j_search_service: self.neo4j_search_service = Neo4jSearchService(self.neo4j_conn)
        self._update_ui_for_current_connection()

    def _set_db_type_cassandra(self):
        if self.current_db_type == "cassandra" and self.cassandra_rb.isChecked(): return
        self.current_db_type = "cassandra"
        self._update_button_group("cassandra")
        self._set_db_type_cassandra_ui_elements()
        self._update_operators()
        if self.cassandra_conn and self.cassandra_conn.get_session():
            if not self.cassandra_meta_fetcher: self.cassandra_meta_fetcher = CassandraMetadataFetcher(
                self.cassandra_conn)
            if not self.cassandra_search_service: self.cassandra_search_service = CassandraSearchService(
                self.cassandra_conn, self.cassandra_meta_fetcher)
        self._update_ui_for_current_connection()

    def _update_ui_for_current_connection(self):
        is_connected = False
        db_name_for_status = ""

        if self.current_db_type == "mongodb" and self.mongo_conn and self.mongo_conn.get_client():
            is_connected = True;
            db_name_for_status = "MongoDB"
            self._load_databases()
        elif self.current_db_type == "neo4j" and self.neo4j_conn and self.neo4j_conn.get_driver():
            is_connected = True;
            db_name_for_status = "Neo4j"
            self._load_neo4j_labels()
        elif self.current_db_type == "cassandra" and self.cassandra_conn and self.cassandra_conn.get_session():
            is_connected = True;
            db_name_for_status = "Cassandra"
            self._load_cassandra_keyspaces()

        if is_connected:
            self.connection_status.setText(f"Połączono ({db_name_for_status})");
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Przełącz")
            self.search_btn.setEnabled(True);
            self.clear_btn.setEnabled(True)
        else:
            self.connection_status.setText("Niepołączono");
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setText("Połącz")
            self.search_btn.setEnabled(False);
            self.clear_btn.setEnabled(False)
            self.db_combo.clear();
            self.entity_combo.clear();
            self.field_combo.clear()
            self._clear_search_ui_and_results()

    def _update_operators(self):
        self.operator_combo.clear()
        ops = []
        if self.current_db_type == "mongodb":
            ops = ["równa się (=)", "nie równa się (!=)", "większe niż (>)", "większe lub równe (>=)",
                   "mniejsze niż (<)", "mniejsze lub równe (<=)", "zawiera", "zaczyna się od", "kończy się na"]
        elif self.current_db_type == "neo4j":
            ops = ["równa się (=)", "nie równa się (!=)", "większe niż (>)", "większe lub równe (>=)",
                   "mniejsze niż (<)", "mniejsze lub równe (<=)", "zawiera", "zaczyna się od", "kończy się na",
                   "istnieje relacja z"]
        elif self.current_db_type == "cassandra":
            ops = ["równa się (=)", "nie równa się (!=)", "większe niż (>)", "większe lub równe (>=)",
                   "mniejsze niż (<)", "mniejsze lub równe (<=)", "zawiera", "zaczyna się od", "kończy się na"]
        self.operator_combo.addItems(ops)

    def _connect_to_db(self):
        self._close_all_connections_and_clear_services()

        if self.current_db_type == "mongodb":
            self._connect_to_mongodb()
        elif self.current_db_type == "neo4j":
            self._connect_to_neo4j()
        elif self.current_db_type == "cassandra":
            self._connect_to_cassandra_search()
        self._update_ui_for_current_connection()

    def _close_all_connections_and_clear_services(self):
        if self.mongo_conn: self.mongo_conn.close()
        if self.neo4j_conn: self.neo4j_conn.close()
        if self.cassandra_conn: self.cassandra_conn.close()
        self.mongo_conn = self.neo4j_conn = self.cassandra_conn = None
        self.mongo_meta_fetcher = self.neo4j_meta_fetcher = self.cassandra_meta_fetcher = None
        self.mongo_search_service = self.neo4j_search_service = self.cassandra_search_service = None

    def _connect_to_mongodb(self):
        connection_string = self.connection_input.text().strip()
        self.mongo_conn = MongoConnection(connection_string)
        success, message = self.mongo_conn.connect()
        if success:
            self.mongo_meta_fetcher = MongoMetadataFetcher(self.mongo_conn)
            self.mongo_search_service = MongoSearchService(self.mongo_conn)
        else:
            self.mongo_conn = None
            QMessageBox.critical(self, "Błąd", message)

    def _connect_to_neo4j(self):
        uri = self.connection_input.text().strip();
        username = self.neo4j_user_input.text().strip();
        password = self.neo4j_pass_input.text()
        self.neo4j_conn = Neo4jConnection(uri, username, password)
        success, message = self.neo4j_conn.connect()
        if success:
            self.neo4j_meta_fetcher = Neo4jMetadataFetcher(self.neo4j_conn)
            self.neo4j_search_service = Neo4jSearchService(self.neo4j_conn)
        else:
            self.neo4j_conn = None
            QMessageBox.critical(self, "Błąd", message)

    def _connect_to_cassandra_search(self):
        contact_points_str = self.connection_input.text().strip()
        username = self.cassandra_user_input_search.text().strip()
        password = self.cassandra_pass_input_search.text()
        if not contact_points_str: QMessageBox.warning(self, "Błąd Wejścia",
                                                       "Contact Points nie mogą być puste."); return
        contact_points = [p.strip() for p in contact_points_str.split(',') if p.strip()]
        if not contact_points: QMessageBox.warning(self, "Błąd Wejścia", "Nieprawidłowy format Contact Points."); return

        self.cassandra_conn = CassandraConnection(contact_points, username, password)
        success, message = self.cassandra_conn.connect()
        if success:
            self.cassandra_meta_fetcher = CassandraMetadataFetcher(self.cassandra_conn)
            self.cassandra_search_service = CassandraSearchService(self.cassandra_conn, self.cassandra_meta_fetcher)
        else:
            self.cassandra_conn = None
            QMessageBox.critical(self, "Błąd", message)

    def _load_databases(self):
        if not self.mongo_meta_fetcher: return
        self.db_combo.clear()
        db_names = self.mongo_meta_fetcher.list_databases()
        if db_names:
            self.db_combo.addItems(db_names)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", "Nie można załadować baz danych MongoDB.")

    def _load_neo4j_labels(self):
        if not self.neo4j_meta_fetcher: return
        self.db_combo.clear();
        self.db_combo.addItem("Neo4j Graph");
        self.db_combo.setCurrentIndex(0)
        self.entity_combo.clear()
        labels = self.neo4j_meta_fetcher.list_labels()
        if labels:
            self.entity_combo.addItems(labels)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", "Nie można załadować etykiet Neo4j.")

    def _load_cassandra_keyspaces(self):
        if not self.cassandra_meta_fetcher: return
        self.db_combo.clear()
        keyspaces = self.cassandra_meta_fetcher.list_keyspaces()
        if keyspaces:
            self.db_combo.addItems(keyspaces)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", "Nie można załadować keyspace'ów Cassandra.")

    def _update_entities_combo(self, selected_db_name: str):
        self.entity_combo.clear();
        self.field_combo.clear()
        self.current_db_name = selected_db_name
        if not selected_db_name: return

        entities = []
        error_msg = ""
        if self.current_db_type == "mongodb" and self.mongo_meta_fetcher:
            entities = self.mongo_meta_fetcher.list_collections(selected_db_name)
            if not entities and selected_db_name: error_msg = "Nie można załadować kolekcji MongoDB."
        elif self.current_db_type == "neo4j":
            return
        elif self.current_db_type == "cassandra" and self.cassandra_meta_fetcher:
            entities = self.cassandra_meta_fetcher.list_tables(selected_db_name)
            if not entities and selected_db_name: error_msg = f"Nie można załadować tabel dla keyspace '{selected_db_name}'."

        if entities:
            self.entity_combo.addItems(entities)
        elif error_msg:
            QMessageBox.warning(self, "Ostrzeżenie", error_msg)

    def _update_search_fields(self, selected_entity_name: str):
        self.field_combo.clear()
        self.current_entity_name = selected_entity_name
        self.value_input.clear()
        if not selected_entity_name: return

        fields = []
        error_msg = ""
        if self.current_db_type == "mongodb" and self.mongo_meta_fetcher:
            fields = self.mongo_meta_fetcher.get_collection_fields(self.current_db_name, selected_entity_name)
            if not fields and selected_entity_name: error_msg = f"Nie można załadować pól dla kolekcji '{selected_entity_name}'."
        elif self.current_db_type == "neo4j" and self.neo4j_meta_fetcher:
            fields = self.neo4j_meta_fetcher.get_label_properties(selected_entity_name)
            if not fields and selected_entity_name: error_msg = f"Nie można załadować właściwości dla etykiety '{selected_entity_name}'."
        elif self.current_db_type == "cassandra" and self.cassandra_meta_fetcher:
            fields = self.cassandra_meta_fetcher.get_table_columns(self.current_db_name, selected_entity_name)
            if not fields and selected_entity_name: error_msg = f"Nie można załadować kolumn dla tabeli '{self.current_db_name}.{selected_entity_name}'."

        if fields:
            self.field_combo.addItems(fields)
        elif error_msg:
            QMessageBox.warning(self, "Ostrzeżenie", error_msg)

    def _perform_search(self):
        field = self.field_combo.currentText()
        operator = self.operator_combo.currentText()
        value_str = self.value_input.text()

        if self.current_db_type == "mongodb":
            if not self.mongo_search_service: QMessageBox.critical(self, "Błąd",
                                                                   "MongoDB: Serwis wyszukiwania niedostępny."); return
            if not field: QMessageBox.warning(self, "Ostrzeżenie", "Wybierz pole MongoDB."); return
            results, count, error = self.mongo_search_service.search(self.current_db_name, self.current_entity_name,
                                                                     field, operator, value_str)
            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                self.results_count.setText(self.result_display_manager.display_mongodb_results(results, count))
        elif self.current_db_type == "neo4j":
            if not self.neo4j_search_service: QMessageBox.critical(self, "Błąd",
                                                                   "Neo4j: Serwis wyszukiwania niedostępny."); return
            if not self.current_entity_name: QMessageBox.warning(self, "Ostrzeżenie", "Wybierz etykietę Neo4j."); return
            if not field and not ("istnieje relacja z" in operator): QMessageBox.warning(self, "Ostrzeżenie",
                                                                                         "Wybierz pole Neo4j."); return
            results, count, error = self.neo4j_search_service.search(self.current_entity_name, field, operator,
                                                                     value_str)
            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                self.results_count.setText(self.result_display_manager.display_neo4j_results(results, count))
        elif self.current_db_type == "cassandra":
            if not self.cassandra_search_service: QMessageBox.critical(self, "Błąd",
                                                                       "Cassandra: Serwis wyszukiwania niedostępny."); return
            if not self.current_db_name or not self.current_entity_name: QMessageBox.warning(self, "Ostrzeżenie",
                                                                                             "Wybierz keyspace i tabelę Cassandra."); return
            if not field: QMessageBox.warning(self, "Ostrzeżenie", "Wybierz kolumnę Cassandra."); return
            results, count, error = self.cassandra_search_service.search(self.current_db_name, self.current_entity_name,
                                                                         field, operator, value_str)
            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                self.results_count.setText(self.result_display_manager.display_cassandra_results(results, count))

    def _clear_search_ui_and_results(self):
        self.value_input.clear()
        if self.current_db_type == "mongodb":
            self.result_display_manager.clear_results(["Pole", "Wartość"])
        elif self.current_db_type == "neo4j":
            self.result_display_manager.clear_results(["Typ", "Właściwości/Szczegóły"])
        elif self.current_db_type == "cassandra":
            self.result_display_manager.clear_results(["Kolumna", "Wartość"])
        self.results_count.setText("Znaleziono wyników: 0")


class MongoDBTab(QWidget):
    def __init__(self):
        super().__init__()
        self.mongo_conn: Optional[MongoConnection] = None
        self.mongo_meta_fetcher: Optional[MongoMetadataFetcher] = None
        self.mongo_search_service: Optional[MongoSearchService] = None  # For raw queries

        self.current_db_name = ""
        self.current_collection_name = ""  # Store current collection
        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.data_tree)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        # Connection Panel (same as before)
        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.connection_input = QLineEdit("mongodb://localhost:27017/")
        connection_layout.addRow("Connection String:", self.connection_input)
        self.connect_btn = QPushButton("Connect to MongoDB")
        self.connect_btn.clicked.connect(self._connect_to_mongodb)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)

        # Selection Panel (same as before)
        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)
        self.db_combo = QComboBox();
        self.db_combo.setPlaceholderText("Select database")
        self.db_combo.currentTextChanged.connect(self._update_collections_combo)
        selection_layout.addWidget(QLabel("Database:"));
        selection_layout.addWidget(self.db_combo)
        self.collection_combo = QComboBox();
        self.collection_combo.setPlaceholderText("Select collection")
        self.collection_combo.currentTextChanged.connect(self._on_collection_selected)  # Changed to separate method
        selection_layout.addWidget(QLabel("Collection:"));
        selection_layout.addWidget(self.collection_combo)
        main_layout.addWidget(selection_panel)

        # Query Panel
        query_group = QGroupBox("Zapytanie MongoDB (JSON, np. {\"field\": \"value\"} )")  # Find query
        query_layout = QVBoxLayout(query_group)
        self.mongo_query_input = QTextEdit("{}")  # Default to find all
        self.mongo_query_input.setFixedHeight(80)
        query_layout.addWidget(self.mongo_query_input)
        self.execute_mongo_query_btn = QPushButton("Wykonaj Zapytanie")
        self.execute_mongo_query_btn.clicked.connect(self._execute_custom_mongo_query)
        self.execute_mongo_query_btn.setEnabled(False)
        query_layout.addWidget(self.execute_mongo_query_btn)
        main_layout.addWidget(query_group)

        # Results Panel (same as before, but using self.data_tree)
        self.data_tree = QTreeWidget();
        self.data_tree.setHeaderLabels(["Field", "Value"]);
        self.data_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.data_tree)
        self.document_count_label = QLabel("Documents: 0")
        main_layout.addWidget(self.document_count_label)

    def _connect_to_mongodb(self):
        connection_string = self.connection_input.text().strip()
        if self.mongo_conn: self.mongo_conn.close()
        self.mongo_conn = MongoConnection(connection_string)
        success, message = self.mongo_conn.connect()
        if success:
            self.mongo_meta_fetcher = MongoMetadataFetcher(self.mongo_conn)
            self.mongo_search_service = MongoSearchService(self.mongo_conn)  # Initialize service
            self.connection_status.setText("Connected");
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect");
            self.execute_mongo_query_btn.setEnabled(True)  # Enable query button
            self._load_databases()
        else:
            self.mongo_conn = None;
            self.mongo_meta_fetcher = None;
            self.mongo_search_service = None
            self.connection_status.setText(f"Connection failed: {message.split(':')[-1].strip()}");
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", message)
            self.db_combo.clear();
            self.collection_combo.clear();
            self.data_tree.clear();
            self.document_count_label.setText("Documents: 0")
            self.execute_mongo_query_btn.setEnabled(False)

    def _load_databases(self):
        if not self.mongo_meta_fetcher: return
        self.db_combo.clear()
        db_names = self.mongo_meta_fetcher.list_databases()
        if db_names:
            self.db_combo.addItems(db_names)
        else:
            QMessageBox.warning(self, "Warning", "Could not load databases.")

    def _update_collections_combo(self, db_name):
        self.collection_combo.clear();
        self.data_tree.clear();
        self.document_count_label.setText("Documents: 0")
        self.current_db_name = db_name
        self.mongo_query_input.setText("{}")  # Reset query on DB change
        if not db_name or not self.mongo_meta_fetcher: return
        collections = self.mongo_meta_fetcher.list_collections(db_name)
        if collections:
            self.collection_combo.addItems(collections)
        else:
            QMessageBox.warning(self, "Warning", f"Could not load collections for '{db_name}'.")

    def _on_collection_selected(self, collection_name: str):
        self.current_collection_name = collection_name
        self.mongo_query_input.setText("{}")  # Reset query on collection change
        if collection_name:  # Automatically load some data if a collection is selected
            self._execute_custom_mongo_query()  # Execute with default query "{}"
        else:
            self.data_tree.clear()
            self.document_count_label.setText("Documents: 0")

    def _execute_custom_mongo_query(self):
        if not self.mongo_search_service or not self.current_db_name or not self.current_collection_name:
            QMessageBox.warning(self, "Błąd", "Nie wybrano bazy danych/kolekcji lub brak połączenia.")
            return

        query_str = self.mongo_query_input.toPlainText().strip()
        if not query_str:  # Default to find all if empty
            query_str = "{}"
            self.mongo_query_input.setText(query_str)

        results, count, error = self.mongo_search_service.execute_raw_query(
            self.current_db_name, self.current_collection_name, query_str
        )

        if error:
            QMessageBox.critical(self, "Błąd Zapytania MongoDB", error)
            self.document_count_label.setText("Błąd zapytania")
        else:
            status_msg = self.result_display_manager.display_mongodb_results(results, count, is_raw_query=True)
            self.document_count_label.setText(status_msg)


class Neo4jTab(QWidget):
    def __init__(self):
        super().__init__()
        self.neo4j_conn: Optional[Neo4jConnection] = None
        self.neo4j_search_service: Optional[Neo4jSearchService] = None  # For raw Cypher
        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.results_tree)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        connection_panel = QWidget();
        connection_layout = QFormLayout(connection_panel)
        self.uri_input = QLineEdit("bolt://localhost:7687");
        connection_layout.addRow("URI:", self.uri_input)
        self.username_input = QLineEdit("neo4j");
        connection_layout.addRow("Username:", self.username_input)
        self.password_input = QLineEdit();
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password);
        connection_layout.addRow("Password:", self.password_input)
        self.connect_btn = QPushButton("Connect to Neo4j");
        self.connect_btn.clicked.connect(self._connect_to_neo4j);
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Not connected");
        self.connection_status.setStyleSheet("color: red; font-weight: bold;");
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)

        query_panel = QWidget();
        query_layout = QVBoxLayout(query_panel)
        query_layout.addWidget(QLabel("Cypher Query:"))
        self.query_input = QTextEdit("MATCH (n) RETURN n LIMIT 25");
        self.query_input.setMinimumHeight(100);
        query_layout.addWidget(self.query_input)
        self.execute_btn = QPushButton("Execute Query");
        self.execute_btn.clicked.connect(self._execute_raw_cypher_query);
        self.execute_btn.setEnabled(False);
        query_layout.addWidget(self.execute_btn)
        main_layout.addWidget(query_panel)

        samples_panel = QWidget();
        samples_layout = QHBoxLayout(samples_panel)
        samples_layout.addWidget(QLabel("Sample Queries:"))
        self.nodes_btn = QPushButton("All Nodes");
        self.nodes_btn.clicked.connect(lambda: self._set_sample_query("MATCH (n) RETURN n LIMIT 25"))
        self.rels_btn = QPushButton("All Relationships");
        self.rels_btn.clicked.connect(lambda: self._set_sample_query("MATCH ()-[r]->() RETURN r LIMIT 25"))
        self.labels_btn = QPushButton("Node Labels");
        self.labels_btn.clicked.connect(lambda: self._set_sample_query("CALL db.labels() YIELD label RETURN label"))
        self.schema_btn = QPushButton("Schema");
        self.schema_btn.clicked.connect(lambda: self._set_sample_query("CALL db.schema.visualization()"))
        self.sample_buttons = [self.nodes_btn, self.rels_btn, self.labels_btn, self.schema_btn]
        for btn in self.sample_buttons: btn.setEnabled(False); samples_layout.addWidget(btn)
        main_layout.addWidget(samples_panel)

        main_layout.addWidget(QLabel("Results:"))
        self.results_tree = QTreeWidget();
        self.results_tree.setHeaderLabels(["Item", "Value"]);
        self.results_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.results_tree)
        self.results_count_label = QLabel("Results: 0")
        main_layout.addWidget(self.results_count_label)

    def _connect_to_neo4j(self):
        uri = self.uri_input.text().strip();
        username = self.username_input.text().strip();
        password = self.password_input.text()
        if self.neo4j_conn: self.neo4j_conn.close()
        self.neo4j_conn = Neo4jConnection(uri, username, password)
        success, message = self.neo4j_conn.connect()
        if success:
            self.neo4j_search_service = Neo4jSearchService(self.neo4j_conn)  # Init service
            self.connection_status.setText("Connected");
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect");
            self.execute_btn.setEnabled(True)
            for btn in self.sample_buttons: btn.setEnabled(True)
        else:
            self.neo4j_conn = None;
            self.neo4j_search_service = None
            self.connection_status.setText(f"Connection/Auth failed: {message.split(':')[-1].strip()}");
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", message)
            self.execute_btn.setEnabled(False)
            for btn in self.sample_buttons: btn.setEnabled(False)

    def _set_sample_query(self, query):
        self.query_input.setText(query)

    def _execute_raw_cypher_query(self):  # Renamed from _execute_query
        query = self.query_input.toPlainText().strip()
        if not query or not self.neo4j_search_service:
            QMessageBox.warning(self, "Błąd", "Brak zapytania lub połączenia z Neo4j.")
            self.results_count_label.setText("Results: 0")
            self.result_display_manager.clear_results(["Result"])
            return

        records, error = self.neo4j_search_service.execute_raw_cypher(query)

        if error:
            QMessageBox.warning(self, "Query Error", error)
            self.results_count_label.setText("Błąd zapytania")
            self.result_display_manager.clear_results(["Error"])
            self.result_display_manager.tree_widget.addTopLevelItem(QTreeWidgetItem([error]))

        else:
            status_msg = self.result_display_manager.display_neo4j_raw_query_results(records)
            self.results_count_label.setText(status_msg)


class CassandraTab(QWidget):
    def __init__(self):
        super().__init__()
        self.cassandra_conn: Optional[CassandraConnection] = None
        self.cassandra_meta_fetcher: Optional[CassandraMetadataFetcher] = None
        self.cassandra_search_service: Optional[CassandraSearchService] = None  # For raw CQL
        self.current_keyspace = None
        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.data_tree)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        # Connection Panel
        connection_panel = QWidget();
        connection_layout = QFormLayout(connection_panel)
        self.contact_points_input = QLineEdit("127.0.0.1");
        connection_layout.addRow("Contact Points:", self.contact_points_input)
        self.username_input = QLineEdit();
        self.username_input.setPlaceholderText("(Optional)");
        connection_layout.addRow("Username:", self.username_input)
        self.password_input = QLineEdit();
        self.password_input.setPlaceholderText("(Optional)");
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password);
        connection_layout.addRow("Password:", self.password_input)
        self.connect_btn = QPushButton("Connect to Cassandra");
        self.connect_btn.clicked.connect(self._connect_to_cassandra);
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Not connected");
        self.connection_status.setStyleSheet("color: red; font-weight: bold;");
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)

        # Selection Panel (Keyspace is still useful context for raw queries)
        selection_panel = QWidget();
        selection_layout = QHBoxLayout(selection_panel)
        self.keyspace_combo = QComboBox();
        self.keyspace_combo.setPlaceholderText("Select keyspace (for context)");
        self.keyspace_combo.currentTextChanged.connect(self._on_keyspace_selected);
        self.keyspace_combo.setEnabled(False)
        selection_layout.addWidget(QLabel("Keyspace (kontekst):"));
        selection_layout.addWidget(self.keyspace_combo)
        # Table combo might be less relevant if user provides full raw CQL, but can stay for consistency or simple table data view.
        # For now, we'll focus raw query on the main query input.
        # If simple table view is desired, add table_combo and its logic back similar to MongoDBTab.
        main_layout.addWidget(selection_panel)

        # Query Panel
        query_group = QGroupBox("Zapytanie CQL")
        query_layout = QVBoxLayout(query_group)
        self.cql_query_input = QTextEdit("SELECT * FROM system.local LIMIT 10;")  # Example query
        self.cql_query_input.setFixedHeight(100)
        query_layout.addWidget(self.cql_query_input)
        self.execute_cql_query_btn = QPushButton("Wykonaj Zapytanie CQL")
        self.execute_cql_query_btn.clicked.connect(self._execute_custom_cql_query)
        self.execute_cql_query_btn.setEnabled(False)
        query_layout.addWidget(self.execute_cql_query_btn)
        main_layout.addWidget(query_group)

        # Results Panel
        self.data_tree = QTreeWidget();
        self.data_tree.setColumnCount(1);
        self.data_tree.setHeaderLabels(["Row Data"])
        main_layout.addWidget(self.data_tree)
        self.row_count_label = QLabel("Rows: 0")
        main_layout.addWidget(self.row_count_label)

    def _connect_to_cassandra(self):
        contact_points_str = self.contact_points_input.text().strip()
        username = self.username_input.text().strip();
        password = self.password_input.text()
        if not contact_points_str: QMessageBox.warning(self, "Input Error", "Contact Points cannot be empty."); return
        contact_points = [p.strip() for p in contact_points_str.split(',') if p.strip()]
        if not contact_points: QMessageBox.warning(self, "Input Error", "Invalid Contact Points format."); return

        if self.cassandra_conn: self.cassandra_conn.close()
        self.cassandra_conn = CassandraConnection(contact_points, username, password)
        success, message = self.cassandra_conn.connect()

        if success:
            self.cassandra_meta_fetcher = CassandraMetadataFetcher(self.cassandra_conn)
            # Pass meta_fetcher to service if it's needed by it
            self.cassandra_search_service = CassandraSearchService(self.cassandra_conn, self.cassandra_meta_fetcher)
            self.connection_status.setText("Connected");
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect");
            self.keyspace_combo.setEnabled(True)
            self.execute_cql_query_btn.setEnabled(True)
            self._load_keyspaces()
        else:
            self.cassandra_conn = None;
            self.cassandra_meta_fetcher = None;
            self.cassandra_search_service = None
            self.connection_status.setText(f"Connection failed: {message.split(':')[-1].strip()}");
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", message)
            self._reset_ui_on_disconnect_cassandra()

    def _reset_ui_on_disconnect_cassandra(self):
        self.keyspace_combo.clear();
        self.data_tree.clear()  # Removed table_combo specifics
        self.row_count_label.setText("Rows: 0")
        self.keyspace_combo.setEnabled(False)  # Removed table_combo
        self.execute_cql_query_btn.setEnabled(False)
        self.result_display_manager.clear_results(["Row Data"])

    def _load_keyspaces(self):
        if not self.cassandra_meta_fetcher: return
        self.keyspace_combo.clear()
        keyspaces = self.cassandra_meta_fetcher.list_keyspaces()
        if keyspaces:
            self.keyspace_combo.addItems(keyspaces); self.keyspace_combo.setCurrentIndex(-1)
        else:
            QMessageBox.warning(self, "Warning", "Could not load keyspaces.")
        self.current_keyspace = None  # Reset current keyspace

    def _on_keyspace_selected(self, keyspace_name: str):
        self.current_keyspace = keyspace_name
        if self.cassandra_conn and self.cassandra_conn.get_session() and keyspace_name:
            try:
                # Attempt to set keyspace on session for context, but queries should be fully qualified if possible
                self.cassandra_conn.get_session().set_keyspace(keyspace_name)
            except InvalidRequest:
                QMessageBox.warning(self, "Keyspace Błąd",
                                    f"Nie można ustawić keyspace '{keyspace_name}'. Może nie istnieć lub jest niedostępny.")
                self.current_keyspace = None  # Reset if set_keyspace fails
                self.keyspace_combo.setCurrentText("")  # Clear selection in combo
            # No automatic data load here, user uses the raw query input

    def _execute_custom_cql_query(self):
        cql_query = self.cql_query_input.toPlainText().strip()
        if not cql_query:
            QMessageBox.warning(self, "Błąd", "Zapytanie CQL nie może być puste.")
            return
        if not self.cassandra_search_service:
            QMessageBox.warning(self, "Błąd", "Brak połączenia z Cassandra lub serwis niedostępny.")
            return

        # If a keyspace is selected, ensure the session is using it (best effort)
        # However, raw CQL should ideally specify keyspace if needed, e.g., "SELECT * FROM mykeyspace.mytable"
        if self.current_keyspace and self.cassandra_conn.get_session():
            try:
                self.cassandra_conn.get_session().set_keyspace(self.current_keyspace)
            except InvalidRequest:
                pass  # Silently ignore if keyspace can't be set, query might be self-contained

        rows, error = self.cassandra_search_service.execute_raw_cql(cql_query)

        if error:
            QMessageBox.critical(self, "Błąd Zapytania CQL", error)
            self.row_count_label.setText("Błąd zapytania")
        else:
            # For Cassandra, the 'count' from service is len(rows) due to LIMIT in typical queries
            # For raw query, it's just len(rows) returned
            status_msg = self.result_display_manager.display_cassandra_results(rows, len(rows), is_raw_query=True)
            self.row_count_label.setText(status_msg)


class DatabaseViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Database Data Viewer")
        self.setGeometry(100, 100, 1000, 800)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.search_tab = SearchTab()
        self.mongo_tab = MongoDBTab()
        self.neo4j_tab = Neo4jTab()
        self.cassandra_tab = CassandraTab()

        self.tabs.addTab(self.search_tab, "Wyszukaj")
        self.tabs.addTab(self.mongo_tab, "MongoDB (Przeglądaj/Query)")
        self.tabs.addTab(self.neo4j_tab, "Neo4j (Query)")
        self.tabs.addTab(self.cassandra_tab, "Cassandra (Przeglądaj/Query)")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DatabaseViewerApp()
    window.show()
    sys.exit(app.exec())