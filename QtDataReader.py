import sys
import json
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QLineEdit, QFormLayout, QTabWidget,
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
from cassandra.query import SimpleStatement
from cassandra import InvalidRequest


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


class MetadataFetcher:

    def attempt_type_conversion(self, value_str: str) -> Any:
        if value_str.lower() == "true": return True
        if value_str.lower() == "false": return False
        try:
            return int(value_str)
        except ValueError:
            try:
                return float(value_str)
            except ValueError:
                return value_str


class MongoMetadataFetcher(MetadataFetcher):
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


class Neo4jMetadataFetcher(MetadataFetcher):
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
                    result = session.run("CALL db.labels()")
                    return sorted([record["label"] for record in result])
            except Exception:
                return []

    def get_label_properties(self, label_name: str) -> List[str]:
        driver = self.conn.get_driver()
        if not driver or not label_name: return []
        try:
            safe_label_name = label_name.replace('`', '``')
            query = f"MATCH (n:`{safe_label_name}`) WITH n LIMIT 100 UNWIND keys(n) AS prop RETURN DISTINCT prop ORDER BY prop"
            with driver.session(database="neo4j") as session:
                result = session.run(query)
                return [record["prop"] for record in result]
        except Exception:
            return []


class CassandraMetadataFetcher(MetadataFetcher):
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


class SearchService:

    def attempt_type_conversion(self, value_str: str) -> Any:
        if value_str.lower() == "true": return True
        if value_str.lower() == "false": return False
        try:
            return int(value_str)
        except ValueError:
            try:
                return float(value_str)
            except ValueError:
                return value_str


class MongoSearchService(SearchService):
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
            query_value = self.attempt_type_conversion(value_str)
            query = self._build_query(field, operator, query_value)
            results = list(collection.find(query).limit(100))
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
            if query_str.strip():
                try:
                    parsed_query = json.loads(query_str)
                    if not isinstance(parsed_query, dict):
                        return [], 0, "Invalid query format: Query must be a JSON object string."
                except json.JSONDecodeError as je:
                    return [], 0, f"Invalid query format: Not a valid JSON. Error: {str(je)}"

            results = list(collection.find(parsed_query).limit(limit))
            count = collection.count_documents(parsed_query)
            return results, count, None
        except OperationFailure as oe:
            return [], 0, f"MongoDB Operation Failure: {str(oe)}"
        except Exception as e:
            return [], 0, f"MongoDB Raw Query Error: {str(e)}"


class Neo4jSearchService(SearchService):
    def __init__(self, neo4j_connection: Neo4jConnection):
        self.conn = neo4j_connection

    def _build_query(self, label: str, field: str, operator: str, value: Any) -> Tuple[str, Dict]:
        params = {"value": value}
        safe_label = label.replace('`', '``')

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
            query_value = self.attempt_type_conversion(value_str)
            query_str, params = self._build_query(label, field, operator, query_value)

            neo4j_results = {"nodes": [], "relationships": [], "paths": [], "raw_records": []}
            count = 0
            with driver.session(database="neo4j") as session:
                result_cursor = session.run(query_str, parameters=params)
                record_list = list(result_cursor)
                count = len(record_list)
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
                records_as_dicts = [record.data() for record in result_cursor]
                return records_as_dicts, None
        except CypherSyntaxError as cse:
            return [], f"Neo4j Cypher Syntax Error: {str(cse)}"
        except Exception as e:
            return [], f"Neo4j Raw Query Error: {str(e)}"


class CassandraSearchService(SearchService):
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
        return self.attempt_type_conversion(value_str)

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
            count = len(rows)
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
            statement = SimpleStatement(cql_query, fetch_size=100)
            rows = list(session.execute(statement))
            return rows, None
        except InvalidRequest as ir:
            return [], f"Cassandra Invalid CQL Request: {str(ir)}"
        except Exception as e:
            return [], f"Cassandra Raw Query Error: {str(e)}"


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
            if parent_tree_item.columnCount() > 1 and parent_tree_item.text(1) == "":
                parent_tree_item.setText(1, str(data_item))
            elif parent_tree_item.columnCount() == 1 and parent_tree_item.text(0) == "":
                parent_tree_item.setText(0, str(data_item))
            elif parent_tree_item.columnCount() == 1:
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
        if is_raw_query:
            for i, doc in enumerate(results):
                doc_item = QTreeWidgetItem([f"Dokument {i + 1}"])
                self._add_data_to_node(doc, doc_item, "mongodb")
                self.tree_widget.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)
        else:
            for i, doc in enumerate(results):
                doc_id = doc.get('_id', f'Dokument {i + 1}')
                doc_item = QTreeWidgetItem([f"Dokument: {doc_id}"])
                self._add_data_to_node(doc, doc_item, "mongodb")
                self.tree_widget.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)

        return f"Znaleziono dokumentów: {count} (wyświetlono: {len(results)})"

    def display_neo4j_results(self, results_data: Dict[str, List], count: int) -> str:
        self.clear_results(["Typ", "Właściwości/Szczegóły"])
        if results_data.get("nodes"):
            parent = QTreeWidgetItem(["Węzły", f"{len(results_data['nodes'])} znaleziono"])
            self.tree_widget.addTopLevelItem(parent)
            for node in results_data['nodes']:
                labels_str = ", ".join(node.labels) if node.labels else "Brak etykiet"
                item = QTreeWidgetItem([f"Węzeł ({labels_str})", f"id: {node.element_id}"])
                self._add_data_to_node(dict(node.items()), item, "neo4j")
                parent.addChild(item)
            parent.setExpanded(True)
        if results_data.get("relationships"):
            parent = QTreeWidgetItem(["Relacje", f"{len(results_data['relationships'])} znaleziono"])
            self.tree_widget.addTopLevelItem(parent)
            for rel in results_data['relationships']:
                item = QTreeWidgetItem([f"Relacja ({rel.type})", f"id: {rel.element_id}"])
                item.addChild(
                    QTreeWidgetItem(["Od", f"({', '.join(rel.start_node.labels)}) id: {rel.start_node.element_id}"]))
                item.addChild(
                    QTreeWidgetItem(["Do", f"({', '.join(rel.end_node.labels)}) id: {rel.end_node.element_id}"]))
                self._add_data_to_node(dict(rel.items()), item, "neo4j")
                parent.addChild(item)
            parent.setExpanded(True)
        if results_data.get("paths"):
            parent = QTreeWidgetItem(["Ścieżki", f"{len(results_data['paths'])} znaleziono"])
            self.tree_widget.addTopLevelItem(parent)
            for i, path_val in enumerate(results_data['paths']):
                item = QTreeWidgetItem([f"Ścieżka {i + 1}", f"Długość: {len(path_val.relationships)}"])
                parent.addChild(item)
            parent.setExpanded(True)
        if results_data.get("raw_records"):
            parent = QTreeWidgetItem(["Inne Wyniki", f"{len(results_data['raw_records'])} rekordów"])
            self.tree_widget.addTopLevelItem(parent)
            for i, record_val in enumerate(results_data['raw_records']):
                item = QTreeWidgetItem([f"Rekord {i + 1}"])
                self._add_data_to_node(dict(record_val.items()), item, "neo4j")
                parent.addChild(item)
            parent.setExpanded(True)
        return f"Znaleziono wyników: {count}"

    def display_neo4j_raw_query_results(self, records: List[Dict]) -> str:
        self.clear_results()
        if not records:
            self.tree_widget.setHeaderLabels(["Wynik"])
            self.tree_widget.addTopLevelItem(QTreeWidgetItem(["Zapytanie wykonane, brak rekordów."]))
            return "Wyniki: 0"

        if records[0]:
            self.tree_widget.setHeaderLabels(list(records[0].keys()))
            self.tree_widget.setColumnCount(len(records[0].keys()))
        else:
            self.tree_widget.setHeaderLabels(["Pusty Rekord"])
            self.tree_widget.setColumnCount(1)

        for i, record_dict in enumerate(records):
            if len(record_dict.keys()) == 1:
                key = list(record_dict.keys())[0]
                row_item_text = str(record_dict[key]) if not isinstance(record_dict[key], (dict,
                                                                                           list)) else f"Rekord {i + 1} (Szczegóły poniżej)"
                item = QTreeWidgetItem([row_item_text])
                if isinstance(record_dict[key], (dict, list)):
                    self._add_data_to_node(record_dict[key], item, "neo4j")
                    item.setExpanded(True)
            else:
                item = QTreeWidgetItem([f"Rekord {i + 1}"])
                for key, value in record_dict.items():
                    child_item = QTreeWidgetItem([str(key)])
                    self._add_data_to_node(value, child_item, "neo4j")
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
            for i in range(len(column_names)):
                self.tree_widget.resizeColumnToContents(i)
        elif results:
            self.tree_widget.setHeaderLabels(["Wynik Cassandra"])
            self.tree_widget.setColumnCount(1)
            self.tree_widget.addTopLevelItem(QTreeWidgetItem([str(results)]))
        else:
            self.tree_widget.setHeaderLabels(["Wyniki Cassandra"])
            self.tree_widget.setColumnCount(1)
            self.tree_widget.addTopLevelItem(QTreeWidgetItem(["Brak wyników"]))

        return f"Zwrócono wierszy: {len(results)}"


class MongoDBTab(QWidget):
    def __init__(self):
        super().__init__()
        self.mongo_conn: Optional[MongoConnection] = None
        self.mongo_meta_fetcher: Optional[MongoMetadataFetcher] = None
        self.mongo_search_service: Optional[MongoSearchService] = None

        self.current_db_name = ""
        self.current_collection_name = ""
        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.data_tree)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.connection_input = QLineEdit("mongodb://localhost:27017/")
        connection_layout.addRow("Connection String:", self.connection_input)
        self.connect_btn = QPushButton("Połącz z MongoDB")
        self.connect_btn.clicked.connect(self._connect_to_mongodb)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Niepołączono")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)

        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)

        db_layout = QVBoxLayout()
        db_layout.addWidget(QLabel("Baza danych:"))
        self.db_combo = QComboBox()
        self.db_combo.setPlaceholderText("Wybierz bazę danych")
        self.db_combo.currentTextChanged.connect(self._on_database_selected)
        db_layout.addWidget(self.db_combo)
        selection_layout.addLayout(db_layout)

        collection_layout = QVBoxLayout()
        collection_layout.addWidget(QLabel("Kolekcja:"))
        self.collection_combo = QComboBox()
        self.collection_combo.setPlaceholderText("Wybierz kolekcję")
        self.collection_combo.currentTextChanged.connect(self._on_collection_selected)
        collection_layout.addWidget(self.collection_combo)
        selection_layout.addLayout(collection_layout)

        main_layout.addWidget(selection_panel)

        self.search_tabs = QTabWidget()

        self.structural_search_tab = QWidget()
        structural_search_layout = QFormLayout(self.structural_search_tab)

        self.field_combo = QComboBox()
        structural_search_layout.addRow("Pole:", self.field_combo)

        self.operator_combo = QComboBox()
        self.operator_combo.addItems([
            "równa się", "nie równa się", "większe niż", "większe lub równe",
            "mniejsze niż", "mniejsze lub równe", "zawiera", "zaczyna się od", "kończy się na"
        ])
        structural_search_layout.addRow("Operator:", self.operator_combo)

        self.value_input = QLineEdit()
        structural_search_layout.addRow("Wartość:", self.value_input)

        self.structural_search_btn = QPushButton("Wyszukaj")
        self.structural_search_btn.clicked.connect(self._perform_structural_search)
        self.structural_search_btn.setEnabled(False)
        structural_search_layout.addRow(self.structural_search_btn)

        self.query_tab = QWidget()
        query_layout = QVBoxLayout(self.query_tab)

        query_type_layout = QHBoxLayout()
        self.query_type_combo = QComboBox()
        self.query_type_combo.addItems([
            "find() - Wyszukiwanie dokumentów",
            "aggregate() - Pipeline agregacji",
            "distinct() - Unikalne wartości",
            "count_documents() - Liczenie dokumentów",
            "find_one() - Jeden dokument"
        ])
        self.query_type_combo.currentTextChanged.connect(self._on_query_type_changed)
        query_type_layout.addWidget(QLabel("Typ zapytania:"))
        query_type_layout.addWidget(self.query_type_combo)
        query_layout.addLayout(query_type_layout)

        query_layout.addWidget(QLabel("Zapytanie (JSON):"))
        self.mongo_query_input = QTextEdit('{}')
        self.mongo_query_input.setMinimumHeight(120)
        query_layout.addWidget(self.mongo_query_input)

        self.execute_mongo_query_btn = QPushButton("Wykonaj Zapytanie")
        self.execute_mongo_query_btn.clicked.connect(self._execute_database_query)
        self.execute_mongo_query_btn.setEnabled(False)
        query_layout.addWidget(self.execute_mongo_query_btn)

        samples_layout = QHBoxLayout()
        samples_layout.addWidget(QLabel("Przykłady:"))
        self.sample_find_btn = QPushButton("Find All")
        self.sample_find_btn.clicked.connect(lambda: self._set_sample_query("find", '{}'))
        self.sample_aggregate_btn = QPushButton("Aggregate")
        self.sample_aggregate_btn.clicked.connect(
            lambda: self._set_sample_query("aggregate", '[{"$match": {}}, {"$limit": 10}]'))
        self.sample_distinct_btn = QPushButton("Distinct")
        self.sample_distinct_btn.clicked.connect(lambda: self._set_sample_query("distinct", '"field_name"'))

        for btn in [self.sample_find_btn, self.sample_aggregate_btn, self.sample_distinct_btn]:
            btn.setEnabled(False)
            samples_layout.addWidget(btn)
        samples_layout.addStretch()
        query_layout.addLayout(samples_layout)

        self.search_tabs.addTab(self.structural_search_tab, "Wyszukiwanie strukturalne")
        self.search_tabs.addTab(self.query_tab, "Zapytania MongoDB")

        main_layout.addWidget(self.search_tabs)

        self.data_tree = QTreeWidget()
        self.data_tree.setHeaderLabels(["Pole", "Wartość"])
        self.data_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.data_tree)
        self.document_count_label = QLabel("Dokumenty: 0")
        main_layout.addWidget(self.document_count_label)

    def _connect_to_mongodb(self):
        connection_string = self.connection_input.text().strip()
        if self.mongo_conn:
            self.mongo_conn.close()
        self.mongo_conn = MongoConnection(connection_string)
        success, message = self.mongo_conn.connect()
        if success:
            self.mongo_meta_fetcher = MongoMetadataFetcher(self.mongo_conn)
            self.mongo_search_service = MongoSearchService(self.mongo_conn)
            self.connection_status.setText("Połączono")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Połącz ponownie")
            self.execute_mongo_query_btn.setEnabled(True)
            self.structural_search_btn.setEnabled(True)
            for btn in [self.sample_find_btn, self.sample_aggregate_btn, self.sample_distinct_btn]:
                btn.setEnabled(True)
            self._load_databases()
        else:
            self.mongo_conn = None
            self.mongo_meta_fetcher = None
            self.mongo_search_service = None
            self.connection_status.setText(f"Błąd połączenia: {message.split(':')[-1].strip()}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd połączenia", message)
            self._reset_ui()

    def _reset_ui(self):
        self.db_combo.clear()
        self.collection_combo.clear()
        self.field_combo.clear()
        self.data_tree.clear()
        self.document_count_label.setText("Dokumenty: 0")
        self.execute_mongo_query_btn.setEnabled(False)
        self.structural_search_btn.setEnabled(False)
        for btn in [self.sample_find_btn, self.sample_aggregate_btn, self.sample_distinct_btn]:
            btn.setEnabled(False)
        if hasattr(self, 'current_selection_label'):
            self.current_selection_label.setText("Wybrana kolekcja: Brak")

    def _load_databases(self):
        if not self.mongo_meta_fetcher:
            return
        self.db_combo.clear()
        db_names = self.mongo_meta_fetcher.list_databases()
        if db_names:
            self.db_combo.addItems(db_names)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", "Nie można załadować baz danych.")

    def _on_database_selected(self, db_name):
        self.current_db_name = db_name
        self.collection_combo.clear()
        self.field_combo.clear()
        self.data_tree.clear()
        self.document_count_label.setText("Dokumenty: 0")

        if db_name and self.mongo_meta_fetcher:
            collections = self.mongo_meta_fetcher.list_collections(db_name)
            if collections:
                self.collection_combo.addItems(collections)

    def _on_collection_selected(self, collection_name):
        self.current_collection_name = collection_name
        self._update_fields_combo()

        if hasattr(self, 'current_selection_label'):
            if collection_name:
                self.current_selection_label.setText(f"Wybrana kolekcja: {collection_name}")
            else:
                self.current_selection_label.setText("Wybrana kolekcja: Brak")

        if collection_name and self.mongo_conn:
            self.execute_mongo_query_btn.setEnabled(True)
        else:
            self.execute_mongo_query_btn.setEnabled(False)

    def _update_fields_combo(self):
        self.field_combo.clear()
        self.field_combo.addItem("None")

        if not self.current_db_name or not self.current_collection_name or not self.mongo_meta_fetcher:
            return
        fields = self.mongo_meta_fetcher.get_collection_fields(self.current_db_name, self.current_collection_name)
        if fields:
            self.field_combo.addItems(fields)

    def _perform_structural_search(self):
        if not self.mongo_search_service:
            QMessageBox.critical(self, "Błąd", "MongoDB: Serwis wyszukiwania niedostępny.")
            return
        if not self.current_db_name or not self.current_collection_name:
            QMessageBox.warning(self, "Ostrzeżenie", "Wybierz bazę danych i kolekcję.")
            return

        field = self.field_combo.currentText()

        if field.startswith("None"):
            results, count, error = self.mongo_search_service.execute_raw_query(
                self.current_db_name, self.current_collection_name, '{}', limit=100
            )
        else:
            operator = self.operator_combo.currentText()
            value_str = self.value_input.text()

            if not field:
                QMessageBox.warning(self, "Ostrzeżenie", "Wybierz pole.")
                return

            results, count, error = self.mongo_search_service.search(
                self.current_db_name, self.current_collection_name, field, operator, value_str
            )

        if error:
            QMessageBox.critical(self, "Błąd", error)
        else:
            self.document_count_label.setText(
                self.result_display_manager.display_mongodb_results(results, count)
            )

    def _on_query_type_changed(self, query_type):
        if "find()" in query_type:
            self._set_sample_query("find", '{}')
        elif "aggregate()" in query_type:
            self._set_sample_query("aggregate", '[{"$match": {}}, {"$limit": 10}]')
        elif "distinct()" in query_type:
            self._set_sample_query("distinct", '"field_name"')
        elif "count_documents()" in query_type:
            self._set_sample_query("count", '{}')

    def _set_sample_query(self, query_type, query):
        if query_type == "find":
            self.query_type_combo.setCurrentText("find() - Wyszukiwanie dokumentów")
        elif query_type == "aggregate":
            self.query_type_combo.setCurrentText("aggregate() - Pipeline agregacji")
        elif query_type == "distinct":
            self.query_type_combo.setCurrentText("distinct() - Unikalne wartości")
        elif query_type == "count":
            self.query_type_combo.setCurrentText("count_documents() - Liczenie dokumentów")

        self.mongo_query_input.setText(query)

    def _execute_database_query(self):
        if not self.mongo_conn or not self.current_db_name:
            QMessageBox.warning(self, "Błąd", "Nie wybrano bazy danych lub brak połączenia.")
            return

        if not self.current_collection_name:
            QMessageBox.warning(self, "Błąd", "Wybierz kolekcję z listy rozwijanej.")
            return

        query_str = self.mongo_query_input.toPlainText().strip()
        if not query_str:
            QMessageBox.warning(self, "Błąd", "Podaj zapytanie.")
            return

        query_type = self.query_type_combo.currentText()

        try:
            client = self.mongo_conn.get_client()
            db = client[self.current_db_name]
            collection = db[self.current_collection_name]

            if "find()" in query_type:
                self._execute_find_query(collection, query_str)
            elif "aggregate()" in query_type:
                self._execute_aggregate_query(collection, query_str)
            elif "distinct()" in query_type:
                self._execute_distinct_query(collection, query_str)
            elif "count_documents()" in query_type:
                self._execute_count_query(collection, query_str)
            elif "find_one()" in query_type:
                self._execute_find_one_query(collection, query_str)

        except Exception as e:
            QMessageBox.critical(self, "Błąd zapytania", f"Błąd wykonania zapytania: {str(e)}")
            self.document_count_label.setText("Błąd zapytania")

    def _execute_find_query(self, collection, query_str):
        try:
            query = json.loads(query_str) if query_str.strip() != '{}' else {}

            cursor = collection.find(query)
            results = list(cursor)
            count = collection.count_documents(query)

            status_msg = self.result_display_manager.display_mongodb_results(results, count, is_raw_query=True)
            self.document_count_label.setText(status_msg)

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Błąd JSON", f"Nieprawidłowy format JSON: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wykonania find(): {str(e)}")

    def _execute_aggregate_query(self, collection, query_str):
        try:
            pipeline = json.loads(query_str)
            if not isinstance(pipeline, list):
                QMessageBox.critical(self, "Błąd", "Pipeline agregacji musi być listą.")
                return

            results = list(collection.aggregate(pipeline))
            count = len(results)

            status_msg = self.result_display_manager.display_mongodb_results(results, count, is_raw_query=True)
            self.document_count_label.setText(f"Pipeline zwrócił: {count} wyników")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Błąd JSON", f"Nieprawidłowy format JSON: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wykonania aggregate(): {str(e)}")

    def _execute_distinct_query(self, collection, query_str):
        try:
            field_name = json.loads(query_str)
            if not isinstance(field_name, str):
                QMessageBox.critical(self, "Błąd", "Nazwa pola musi być stringiem.")
                return

            results = collection.distinct(field_name)
            count = len(results)

            formatted_results = [{"value": result} for result in results]

            status_msg = self.result_display_manager.display_mongodb_results(formatted_results, count,
                                                                             is_raw_query=True)
            self.document_count_label.setText(f"Distinct zwrócił: {count} unikalnych wartości")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Błąd JSON", f"Nieprawidłowy format JSON: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wykonania distinct(): {str(e)}")

    def _execute_count_query(self, collection, query_str):
        try:
            query = json.loads(query_str) if query_str.strip() != '{}' else {}

            count = collection.count_documents(query)

            self.result_display_manager.clear_results(["Wynik"])
            self.result_display_manager.tree_widget.addTopLevelItem(
                QTreeWidgetItem([f"Liczba dokumentów: {count}"])
            )
            self.document_count_label.setText(f"Znaleziono: {count} dokumentów")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Błąd JSON", f"Nieprawidłowy format JSON: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wykonania count_documents(): {str(e)}")

    def _execute_find_one_query(self, collection, query_str):
        try:
            query = json.loads(query_str) if query_str.strip() != '{}' else {}

            result = collection.find_one(query)

            if result:
                status_msg = self.result_display_manager.display_mongodb_results([result], 1, is_raw_query=True)
                self.document_count_label.setText("Znaleziono: 1 dokument")
            else:
                self.result_display_manager.clear_results(["Wynik"])
                self.result_display_manager.tree_widget.addTopLevelItem(
                    QTreeWidgetItem(["Nie znaleziono dokumentu"])
                )
                self.document_count_label.setText("Nie znaleziono dokumentu")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Błąd JSON", f"Nieprawidłowy format JSON: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wykonania find_one(): {str(e)}")


class Neo4jTab(QWidget):
    def __init__(self):
        super().__init__()
        self.neo4j_conn: Optional[Neo4jConnection] = None
        self.neo4j_meta_fetcher: Optional[Neo4jMetadataFetcher] = None
        self.neo4j_search_service: Optional[Neo4jSearchService] = None
        self.current_label = ""
        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.results_tree)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.uri_input = QLineEdit("bolt://localhost:7687")
        connection_layout.addRow("URI:", self.uri_input)
        self.username_input = QLineEdit("neo4j")
        connection_layout.addRow("Username:", self.username_input)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("Password:", self.password_input)
        self.connect_btn = QPushButton("Połącz z Neo4j")
        self.connect_btn.clicked.connect(self._connect_to_neo4j)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Niepołączono")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)

        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)

        label_layout = QVBoxLayout()
        label_layout.addWidget(QLabel("Etykieta:"))
        self.label_combo = QComboBox()
        self.label_combo.setPlaceholderText("Wybierz etykietę")
        self.label_combo.currentTextChanged.connect(self._on_label_selected)
        label_layout.addWidget(self.label_combo)
        selection_layout.addLayout(label_layout)

        selection_layout.addStretch()

        main_layout.addWidget(selection_panel)

        self.search_tabs = QTabWidget()

        self.structural_search_tab = QWidget()
        structural_search_layout = QFormLayout(self.structural_search_tab)

        self.field_combo = QComboBox()
        structural_search_layout.addRow("Właściwość:", self.field_combo)

        self.operator_combo = QComboBox()
        self.operator_combo.addItems([
            "równa się (=)", "nie równa się (!=)", "większe niż (>)", "większe lub równe (>=)",
            "mniejsze niż (<)", "mniejsze lub równe (<=)", "zawiera", "zaczyna się od", "kończy się na"
        ])
        structural_search_layout.addRow("Operator:", self.operator_combo)

        self.value_input = QLineEdit()
        structural_search_layout.addRow("Wartość:", self.value_input)

        self.search_btn = QPushButton("Wyszukaj")
        self.search_btn.clicked.connect(self._perform_search)
        self.search_btn.setEnabled(False)
        structural_search_layout.addRow(self.search_btn)

        self.query_tab = QWidget()
        query_layout = QVBoxLayout(self.query_tab)

        self.query_input = QTextEdit("MATCH (n) RETURN n LIMIT 25")
        self.query_input.setMinimumHeight(120)
        query_layout.addWidget(self.query_input)

        self.execute_btn = QPushButton("Wykonaj Zapytanie")
        self.execute_btn.clicked.connect(self._execute_raw_cypher_query)
        self.execute_btn.setEnabled(False)
        query_layout.addWidget(self.execute_btn)

        samples_layout = QHBoxLayout()
        samples_layout.addWidget(QLabel("Przykłady:"))
        self.nodes_btn = QPushButton("Wszystkie węzły")
        self.nodes_btn.clicked.connect(lambda: self._set_sample_query("MATCH (n) RETURN n LIMIT 25"))
        self.rels_btn = QPushButton("Wszystkie relacje")
        self.rels_btn.clicked.connect(lambda: self._set_sample_query("MATCH ()-[r]->() RETURN r LIMIT 25"))
        self.labels_btn = QPushButton("Etykiety węzłów")
        self.labels_btn.clicked.connect(lambda: self._set_sample_query("CALL db.labels() YIELD label RETURN label"))
        self.schema_btn = QPushButton("Schemat")
        self.schema_btn.clicked.connect(lambda: self._set_sample_query("CALL db.schema.visualization()"))

        self.sample_buttons = [self.nodes_btn, self.rels_btn, self.labels_btn, self.schema_btn]
        for btn in self.sample_buttons:
            btn.setEnabled(False)
            samples_layout.addWidget(btn)
        query_layout.addLayout(samples_layout)

        self.search_tabs.addTab(self.structural_search_tab, "Wyszukiwanie strukturalne")
        self.search_tabs.addTab(self.query_tab, "Zapytania Cypher")

        main_layout.addWidget(self.search_tabs)

        main_layout.addWidget(QLabel("Wyniki:"))
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Element", "Wartość"])
        self.results_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.results_tree)
        self.results_count_label = QLabel("Wyniki: 0")
        main_layout.addWidget(self.results_count_label)

    def _connect_to_neo4j(self):
        uri = self.uri_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if self.neo4j_conn:
            self.neo4j_conn.close()
        self.neo4j_conn = Neo4jConnection(uri, username, password)
        success, message = self.neo4j_conn.connect()
        if success:
            self.neo4j_meta_fetcher = Neo4jMetadataFetcher(self.neo4j_conn)
            self.neo4j_search_service = Neo4jSearchService(self.neo4j_conn)
            self.connection_status.setText("Połączono")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Połącz ponownie")
            self.execute_btn.setEnabled(True)
            self.search_btn.setEnabled(True)
            for btn in self.sample_buttons:
                btn.setEnabled(True)
            self._load_labels()
        else:
            self.neo4j_conn = None
            self.neo4j_meta_fetcher = None
            self.neo4j_search_service = None
            self.connection_status.setText(f"Błąd połączenia: {message.split(':')[-1].strip()}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd połączenia", message)
            self._reset_ui()

    def _reset_ui(self):
        self.label_combo.clear()
        self.field_combo.clear()
        self.results_tree.clear()
        self.results_count_label.setText("Wyniki: 0")
        self.execute_btn.setEnabled(False)
        self.search_btn.setEnabled(False)
        for btn in self.sample_buttons:
            btn.setEnabled(False)

    def _load_labels(self):
        if not self.neo4j_meta_fetcher:
            return
        self.label_combo.clear()
        labels = self.neo4j_meta_fetcher.list_labels()
        if labels:
            self.label_combo.addItems(labels)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", "Nie można załadować etykiet Neo4j.")

    def _on_label_selected(self, label_name: str):
        self.current_label = label_name
        self._update_fields_combo()

    def _update_fields_combo(self):
        self.field_combo.clear()
        self.field_combo.addItem("None")

        if not self.current_label or not self.neo4j_meta_fetcher:
            return
        fields = self.neo4j_meta_fetcher.get_label_properties(self.current_label)
        if fields:
            self.field_combo.addItems(fields)

    def _perform_search(self):
        field = self.field_combo.currentText()

        if not self.neo4j_search_service:
            QMessageBox.critical(self, "Błąd", "Neo4j: Serwis wyszukiwania niedostępny.")
            return
        if not self.current_label:
            QMessageBox.warning(self, "Ostrzeżenie", "Wybierz etykietę Neo4j.")
            return

        if field.startswith("None"):
            safe_label = self.current_label.replace('`', '``')
            query = f"MATCH (n:`{safe_label}`) RETURN n LIMIT 100"
            records, error = self.neo4j_search_service.execute_raw_cypher(query)

            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                neo4j_results = {"nodes": [], "relationships": [], "paths": [], "raw_records": records}
                count = len(records)
                self.results_count_label.setText(
                    self.result_display_manager.display_neo4j_results(neo4j_results, count)
                )
        else:
            operator = self.operator_combo.currentText()
            value_str = self.value_input.text()

            if not field:
                QMessageBox.warning(self, "Ostrzeżenie", "Wybierz pole Neo4j.")
                return

            results, count, error = self.neo4j_search_service.search(
                self.current_label, field, operator, value_str
            )
            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                self.results_count_label.setText(
                    self.result_display_manager.display_neo4j_results(results, count)
                )

    def _set_sample_query(self, query):
        self.query_input.setText(query)

    def _execute_raw_cypher_query(self):
        query = self.query_input.toPlainText().strip()
        if not query or not self.neo4j_search_service:
            QMessageBox.warning(self, "Błąd", "Brak zapytania lub połączenia z Neo4j.")
            self.results_count_label.setText("Wyniki: 0")
            self.result_display_manager.clear_results(["Wynik"])
            return

        records, error = self.neo4j_search_service.execute_raw_cypher(query)

        if error:
            QMessageBox.warning(self, "Błąd zapytania", error)
            self.results_count_label.setText("Błąd zapytania")
            self.result_display_manager.clear_results(["Błąd"])
            self.result_display_manager.tree_widget.addTopLevelItem(QTreeWidgetItem([error]))
        else:
            status_msg = self.result_display_manager.display_neo4j_raw_query_results(records)
            self.results_count_label.setText(status_msg)


class CassandraTab(QWidget):
    def __init__(self):
        super().__init__()
        self.cassandra_conn: Optional[CassandraConnection] = None
        self.cassandra_meta_fetcher: Optional[CassandraMetadataFetcher] = None
        self.cassandra_search_service: Optional[CassandraSearchService] = None
        self.current_keyspace = ""
        self.current_table = ""
        self._setup_ui()
        self.result_display_manager = ResultDisplayManager(self.data_tree)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.contact_points_input = QLineEdit("127.0.0.1")
        connection_layout.addRow("Contact Points:", self.contact_points_input)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("(Opcjonalne)")
        connection_layout.addRow("Username:", self.username_input)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("(Opcjonalne)")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("Password:", self.password_input)
        self.connect_btn = QPushButton("Połącz z Cassandra")
        self.connect_btn.clicked.connect(self._connect_to_cassandra)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Niepołączono")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)

        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)

        keyspace_layout = QVBoxLayout()
        keyspace_layout.addWidget(QLabel("Keyspace:"))
        self.keyspace_combo = QComboBox()
        self.keyspace_combo.setPlaceholderText("Wybierz keyspace")
        self.keyspace_combo.currentTextChanged.connect(self._on_keyspace_selected)
        self.keyspace_combo.setEnabled(False)
        keyspace_layout.addWidget(self.keyspace_combo)
        selection_layout.addLayout(keyspace_layout)

        table_layout = QVBoxLayout()
        table_layout.addWidget(QLabel("Tabela:"))
        self.table_combo = QComboBox()
        self.table_combo.setPlaceholderText("Wybierz tabelę")
        self.table_combo.currentTextChanged.connect(self._on_table_selected)
        self.table_combo.setEnabled(False)
        table_layout.addWidget(self.table_combo)
        selection_layout.addLayout(table_layout)

        main_layout.addWidget(selection_panel)

        self.search_tabs = QTabWidget()

        self.structural_search_tab = QWidget()
        structural_search_layout = QFormLayout(self.structural_search_tab)

        self.field_combo = QComboBox()
        structural_search_layout.addRow("Kolumna:", self.field_combo)

        self.operator_combo = QComboBox()
        self.operator_combo.addItems([
            "równa się (=)", "nie równa się (!=)", "większe niż (>)", "większe lub równe (>=)",
            "mniejsze niż (<)", "mniejsze lub równe (<=)", "zawiera", "zaczyna się od", "kończy się na"
        ])
        structural_search_layout.addRow("Operator:", self.operator_combo)

        self.value_input = QLineEdit()
        structural_search_layout.addRow("Wartość:", self.value_input)

        self.search_btn = QPushButton("Wyszukaj")
        self.search_btn.clicked.connect(self._perform_search)
        self.search_btn.setEnabled(False)
        structural_search_layout.addRow(self.search_btn)

        self.query_tab = QWidget()
        query_layout = QVBoxLayout(self.query_tab)

        self.cql_query_input = QTextEdit("SELECT * FROM {keyspace}.{table} LIMIT 10;")
        self.cql_query_input.setMinimumHeight(120)
        query_layout.addWidget(self.cql_query_input)

        self.execute_cql_query_btn = QPushButton("Wykonaj Zapytanie CQL")
        self.execute_cql_query_btn.clicked.connect(self._execute_custom_cql_query)
        self.execute_cql_query_btn.setEnabled(False)
        query_layout.addWidget(self.execute_cql_query_btn)

        samples_layout = QHBoxLayout()
        samples_layout.addWidget(QLabel("Przykłady:"))
        self.sample_select_btn = QPushButton("SELECT *")
        self.sample_select_btn.clicked.connect(
            lambda: self._set_sample_query("SELECT * FROM {keyspace}.{table} LIMIT 10;"))
        self.sample_count_btn = QPushButton("COUNT")
        self.sample_count_btn.clicked.connect(
            lambda: self._set_sample_query("SELECT COUNT(*) FROM {keyspace}.{table};"))
        self.sample_keyspaces_btn = QPushButton("Keyspaces")
        self.sample_keyspaces_btn.clicked.connect(
            lambda: self._set_sample_query("SELECT keyspace_name FROM system_schema.keyspaces;"))
        self.sample_describe_btn = QPushButton("Describe Table")
        self.sample_describe_btn.clicked.connect(lambda: self._set_sample_query(
            "SELECT * FROM system_schema.columns WHERE keyspace_name = '{keyspace}' AND table_name = '{table}';"))

        self.sample_buttons = [self.sample_select_btn, self.sample_count_btn, self.sample_keyspaces_btn,
                               self.sample_describe_btn]
        for btn in self.sample_buttons:
            btn.setEnabled(False)
            samples_layout.addWidget(btn)
        query_layout.addLayout(samples_layout)

        self.search_tabs.addTab(self.structural_search_tab, "Wyszukiwanie strukturalne")
        self.search_tabs.addTab(self.query_tab, "Zapytania CQL")

        main_layout.addWidget(self.search_tabs)

        self.data_tree = QTreeWidget()
        self.data_tree.setHeaderLabels(["Kolumna", "Wartość"])
        self.data_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.data_tree)
        self.row_count_label = QLabel("Wiersze: 0")
        main_layout.addWidget(self.row_count_label)

    def _connect_to_cassandra(self):
        contact_points_str = self.contact_points_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not contact_points_str:
            QMessageBox.warning(self, "Błąd Wejścia", "Contact Points nie mogą być puste.")
            return

        contact_points = [p.strip() for p in contact_points_str.split(',') if p.strip()]
        if not contact_points:
            QMessageBox.warning(self, "Błąd Wejścia", "Nieprawidłowy format Contact Points.")
            return

        if self.cassandra_conn:
            self.cassandra_conn.close()

        self.cassandra_conn = CassandraConnection(contact_points, username, password)
        success, message = self.cassandra_conn.connect()

        if success:
            self.cassandra_meta_fetcher = CassandraMetadataFetcher(self.cassandra_conn)
            self.cassandra_search_service = CassandraSearchService(self.cassandra_conn, self.cassandra_meta_fetcher)
            self.connection_status.setText("Połączono")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Połącz ponownie")
            self.keyspace_combo.setEnabled(True)
            self.table_combo.setEnabled(True)
            self.execute_cql_query_btn.setEnabled(True)
            self.search_btn.setEnabled(True)

            for btn in self.sample_buttons:
                btn.setEnabled(True)

            self._load_keyspaces()
        else:
            self.cassandra_conn = None
            self.cassandra_meta_fetcher = None
            self.cassandra_search_service = None
            self.connection_status.setText(f"Błąd połączenia: {message.split(':')[-1].strip()}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd połączenia", message)
            self._reset_ui()

    def _reset_ui(self):
        self.keyspace_combo.clear()
        self.table_combo.clear()
        self.field_combo.clear()
        self.data_tree.clear()
        self.row_count_label.setText("Wiersze: 0")
        self.keyspace_combo.setEnabled(False)
        self.table_combo.setEnabled(False)
        self.execute_cql_query_btn.setEnabled(False)
        self.search_btn.setEnabled(False)
        for btn in self.sample_buttons:
            btn.setEnabled(False)

    def _load_keyspaces(self):
        if not self.cassandra_meta_fetcher:
            return
        self.keyspace_combo.clear()
        keyspaces = self.cassandra_meta_fetcher.list_keyspaces()
        if keyspaces:
            self.keyspace_combo.addItems(keyspaces)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", "Nie można załadować keyspace'ów.")

    def _on_keyspace_selected(self, keyspace_name: str):
        self.table_combo.clear()
        self.field_combo.clear()
        self.data_tree.clear()
        self.row_count_label.setText("Wiersze: 0")
        self.current_keyspace = keyspace_name

        if not keyspace_name or not self.cassandra_meta_fetcher:
            return
        tables = self.cassandra_meta_fetcher.list_tables(keyspace_name)
        if tables:
            self.table_combo.addItems(tables)
        else:
            QMessageBox.warning(self, "Ostrzeżenie", f"Nie można załadować tabel dla keyspace '{keyspace_name}'.")

    def _on_table_selected(self, table_name: str):
        self.current_table = table_name
        self._update_fields_combo()

    def _update_fields_combo(self):
        self.field_combo.clear()
        self.field_combo.addItem("None - pokaż wszystkie wiersze")

        if not self.current_table or not self.cassandra_meta_fetcher:
            return
        fields = self.cassandra_meta_fetcher.get_table_columns(self.current_keyspace, self.current_table)
        if fields:
            self.field_combo.addItems(fields)

    def _perform_search(self):
        field = self.field_combo.currentText()

        if not self.cassandra_search_service:
            QMessageBox.critical(self, "Błąd", "Cassandra: Serwis wyszukiwania niedostępny.")
            return
        if not self.current_keyspace or not self.current_table:
            QMessageBox.warning(self, "Ostrzeżenie", "Wybierz keyspace i tabelę Cassandra.")
            return

        if field.startswith("None"):
            safe_keyspace = '"' + self.current_keyspace.replace('"', '""') + '"'
            safe_table = '"' + self.current_table.replace('"', '""') + '"'
            query = f"SELECT * FROM {safe_keyspace}.{safe_table} LIMIT 100"

            rows, error = self.cassandra_search_service.execute_raw_cql(query)

            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                self.row_count_label.setText(
                    self.result_display_manager.display_cassandra_results(rows, len(rows))
                )
        else:
            operator = self.operator_combo.currentText()
            value_str = self.value_input.text()

            if not field:
                QMessageBox.warning(self, "Ostrzeżenie", "Wybierz kolumnę Cassandra.")
                return

            results, count, error = self.cassandra_search_service.search(
                self.current_keyspace, self.current_table, field, operator, value_str
            )
            if error:
                QMessageBox.critical(self, "Błąd", error)
            else:
                self.row_count_label.setText(
                    self.result_display_manager.display_cassandra_results(results, count)
                )

    def _set_sample_query(self, query_template):
        if self.current_keyspace and self.current_table:
            query = query_template.format(
                keyspace=self.current_keyspace,
                table=self.current_table
            )
        else:
            query = query_template

        self.cql_query_input.setText(query)

    def _execute_custom_cql_query(self):
        cql_query = self.cql_query_input.toPlainText().strip()
        if not cql_query:
            QMessageBox.warning(self, "Błąd", "Zapytanie CQL nie może być puste.")
            return
        if not self.cassandra_search_service:
            QMessageBox.warning(self, "Błąd", "Brak połączenia z Cassandra lub serwis niedostępny.")
            return

        if self.current_keyspace and self.current_table:
            cql_query = cql_query.replace("{keyspace}", self.current_keyspace)
            cql_query = cql_query.replace("{table}", self.current_table)

        if self.current_keyspace and self.cassandra_conn.get_session():
            try:
                self.cassandra_conn.get_session().set_keyspace(self.current_keyspace)
            except InvalidRequest:
                pass

        rows, error = self.cassandra_search_service.execute_raw_cql(cql_query)

        if error:
            QMessageBox.critical(self, "Błąd Zapytania CQL", error)
            self.row_count_label.setText("Błąd zapytania")
        else:
            status_msg = self.result_display_manager.display_cassandra_results(rows, len(rows), is_raw_query=True)
            self.row_count_label.setText(status_msg)


class DatabaseViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Database Data Viewer")
        self.setGeometry(100, 100, 1200, 900)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.mongo_tab = MongoDBTab()
        self.neo4j_tab = Neo4jTab()
        self.cassandra_tab = CassandraTab()

        self.tabs.addTab(self.mongo_tab, "MongoDB")
        self.tabs.addTab(self.neo4j_tab, "Neo4j")
        self.tabs.addTab(self.cassandra_tab, "Cassandra")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DatabaseViewerApp()
    window.show()
    sys.exit(app.exec())