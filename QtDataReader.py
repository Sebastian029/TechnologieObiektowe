import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QLineEdit, QFormLayout, QScrollArea, QTabWidget,
    QTextEdit, QGroupBox
)
from PyQt6.QtCore import Qt
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement, PreparedStatement
from cassandra import InvalidRequest


class SearchTab(QWidget):
    def __init__(self):
        super().__init__()
        self.client = None
        self.driver = None
        self.cassandra_session = None
        self.cassandra_cluster = None

        self.current_db_name = ""
        self.current_entity_name = ""

        self.current_db_type = "mongodb"

        self._setup_ui()
        self._set_db_type_mongodb_ui_elements()

    def _setup_ui(self):
        """Configure the search tab interface."""
        main_layout = QVBoxLayout(self)

        db_type_group = QGroupBox("Typ bazy danych")
        db_type_layout = QHBoxLayout(db_type_group)

        self.mongodb_rb = QPushButton("MongoDB")
        self.mongodb_rb.setCheckable(True)
        self.mongodb_rb.setChecked(True)
        self.mongodb_rb.clicked.connect(self._set_db_type_mongodb)

        self.neo4j_rb = QPushButton("Neo4j")
        self.neo4j_rb.setCheckable(True)
        self.neo4j_rb.clicked.connect(self._set_db_type_neo4j)

        self.cassandra_rb = QPushButton("Cassandra")
        self.cassandra_rb.setCheckable(True)
        self.cassandra_rb.clicked.connect(self._set_db_type_cassandra)

        db_type_layout.addWidget(self.mongodb_rb)
        db_type_layout.addWidget(self.neo4j_rb)
        db_type_layout.addWidget(self.cassandra_rb)
        main_layout.addWidget(db_type_group)

        self.connection_group = QGroupBox("Połączenie z bazą danych")
        connection_layout = QFormLayout()
        self.connection_group.setLayout(connection_layout)

        self.connection_input_label_widget = QLabel("Connection String:")
        self.connection_input = QLineEdit("mongodb://localhost:27017/")
        connection_layout.addRow(self.connection_input_label_widget, self.connection_input)

        self.neo4j_user_label = QLabel("Neo4j Username:")
        self.neo4j_user_input = QLineEdit("neo4j")
        self.neo4j_pass_label = QLabel("Neo4j Password:")
        self.neo4j_pass_input = QLineEdit()
        self.neo4j_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow(self.neo4j_user_label, self.neo4j_user_input)
        connection_layout.addRow(self.neo4j_pass_label, self.neo4j_pass_input)

        self.cassandra_user_label_search = QLabel("Cassandra Username:")
        self.cassandra_user_input_search = QLineEdit()
        self.cassandra_user_input_search.setPlaceholderText("(Optional)")
        self.cassandra_pass_label_search = QLabel("Cassandra Password:")
        self.cassandra_pass_input_search = QLineEdit()
        self.cassandra_pass_input_search.setPlaceholderText("(Optional)")
        self.cassandra_pass_input_search.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow(self.cassandra_user_label_search, self.cassandra_user_input_search)
        connection_layout.addRow(self.cassandra_pass_label_search, self.cassandra_pass_input_search)

        self.connect_btn = QPushButton("Połącz")
        self.connect_btn.clicked.connect(self._connect_to_db)
        connection_layout.addRow(self.connect_btn)

        self.connection_status_label_widget = QLabel("Status:")
        self.connection_status = QLabel("Niepołączono")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow(self.connection_status_label_widget, self.connection_status)
        main_layout.addWidget(self.connection_group)

        self.selection_group = QGroupBox("Wybór danych")
        selection_layout = QFormLayout(self.selection_group)
        self.db_combo_label = QLabel("Baza danych:")
        self.db_combo = QComboBox()
        self.db_combo.currentTextChanged.connect(self._update_entities_combo)
        self.entity_combo_label = QLabel("Kolekcja/Tabela:")
        self.entity_combo = QComboBox()
        self.entity_combo.currentTextChanged.connect(self._update_search_fields)
        selection_layout.addRow(self.db_combo_label, self.db_combo)
        selection_layout.addRow(self.entity_combo_label, self.entity_combo)
        main_layout.addWidget(self.selection_group)

        search_group = QGroupBox("Kryteria wyszukiwania")
        search_layout = QFormLayout(search_group)
        self.field_combo = QComboBox()
        search_layout.addRow("Pole:", self.field_combo)
        self.operator_combo = QComboBox()
        self._update_operators()
        search_layout.addRow("Operator:", self.operator_combo)
        self.value_input = QLineEdit()
        search_layout.addRow("Wartość:", self.value_input)
        self.search_btn = QPushButton("Wyszukaj")
        self.search_btn.clicked.connect(self._perform_search)
        self.search_btn.setEnabled(False)
        search_layout.addRow(self.search_btn)
        self.clear_btn = QPushButton("Wyczyść")
        self.clear_btn.clicked.connect(self._clear_search)
        self.clear_btn.setEnabled(False)
        search_layout.addRow(self.clear_btn)
        main_layout.addWidget(search_group)

        results_group = QGroupBox("Wyniki wyszukiwania")
        results_layout = QVBoxLayout(results_group)
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Pole", "Wartość"])
        self.results_tree.setColumnWidth(0, 300)
        self.results_count = QLabel("Znaleziono wyników: 0")
        results_layout.addWidget(self.results_tree)
        results_layout.addWidget(self.results_count)
        main_layout.addWidget(results_group)

        self._set_db_specific_connection_fields_visibility("mongodb")

    def _set_db_specific_connection_fields_visibility(self, db_type: str):
        is_mongo = db_type == "mongodb"
        is_neo4j = db_type == "neo4j"
        is_cassandra = db_type == "cassandra"

        self.neo4j_user_label.setVisible(is_neo4j)
        self.neo4j_user_input.setVisible(is_neo4j)
        self.neo4j_pass_label.setVisible(is_neo4j)
        self.neo4j_pass_input.setVisible(is_neo4j)

        self.cassandra_user_label_search.setVisible(is_cassandra)
        self.cassandra_user_input_search.setVisible(is_cassandra)
        self.cassandra_pass_label_search.setVisible(is_cassandra)
        self.cassandra_pass_input_search.setVisible(is_cassandra)

    def _set_db_type_mongodb_ui_elements(self):
        self.connection_input.setText("mongodb://localhost:27017/")
        self.connection_input_label_widget.setText("Connection String:")
        self._set_db_specific_connection_fields_visibility("mongodb")
        self.selection_group.setTitle("Wybór bazy danych i kolekcji MongoDB")
        self.db_combo_label.setText("Baza danych:")
        self.entity_combo_label.setText("Kolekcja:")

    def _set_db_type_neo4j_ui_elements(self):
        self.connection_input.setText("bolt://localhost:7687")
        self.neo4j_user_input.setText("neo4j")
        self.neo4j_pass_input.clear()
        self.connection_input_label_widget.setText("URI:")
        self._set_db_specific_connection_fields_visibility("neo4j")
        self.selection_group.setTitle("Wybór danych Neo4j")
        self.db_combo_label.setText("Baza danych:")
        self.entity_combo_label.setText("Etykieta:")

    def _set_db_type_cassandra_ui_elements(self):
        self.connection_input.setText("127.0.0.1")
        self.cassandra_user_input_search.clear()
        self.cassandra_pass_input_search.clear()
        self.connection_input_label_widget.setText("Contact Points:")
        self._set_db_specific_connection_fields_visibility("cassandra")
        self.selection_group.setTitle("Wybór danych Cassandra")
        self.db_combo_label.setText("Keyspace:")
        self.entity_combo_label.setText("Tabela:")

    def _set_db_type_mongodb(self):
        if self.current_db_type == "mongodb" and self.mongodb_rb.isChecked(): return
        self.current_db_type = "mongodb"
        self.mongodb_rb.setChecked(True)
        self.neo4j_rb.setChecked(False)
        self.cassandra_rb.setChecked(False)
        self._set_db_type_mongodb_ui_elements()
        self._update_operators()
        self._clear_connection()

    def _set_db_type_neo4j(self):
        if self.current_db_type == "neo4j" and self.neo4j_rb.isChecked(): return
        self.current_db_type = "neo4j"
        self.mongodb_rb.setChecked(False)
        self.neo4j_rb.setChecked(True)
        self.cassandra_rb.setChecked(False)
        self._set_db_type_neo4j_ui_elements()
        self._update_operators()
        self._clear_connection()

    def _set_db_type_cassandra(self):
        if self.current_db_type == "cassandra" and self.cassandra_rb.isChecked(): return
        self.current_db_type = "cassandra"
        self.mongodb_rb.setChecked(False)
        self.neo4j_rb.setChecked(False)
        self.cassandra_rb.setChecked(True)
        self._set_db_type_cassandra_ui_elements()
        self._update_operators()
        self._clear_connection()

    def _update_operators(self):
        self.operator_combo.clear()
        if self.current_db_type == "mongodb":
            self.operator_combo.addItems([
                "równa się (=)", "nie równa się (!=)", "większe niż (>)",
                "większe lub równe (>=)", "mniejsze niż (<)", "mniejsze lub równe (<=)",
                "zawiera", "zaczyna się od", "kończy się na"
            ])
        elif self.current_db_type == "neo4j":
            self.operator_combo.addItems([
                "równa się (=)", "nie równa się (!=)", "większe niż (>)",
                "większe lub równe (>=)", "mniejsze niż (<)", "mniejsze lub równe (<=)",
                "zawiera", "zaczyna się od", "kończy się na", "istnieje relacja z"
            ])
        elif self.current_db_type == "cassandra":
            self.operator_combo.addItems([
                "równa się (=)",
            ])

    def _connect_to_db(self):
        if self.current_db_type == "mongodb":
            self._connect_to_mongodb()
        elif self.current_db_type == "neo4j":
            self._connect_to_neo4j()
        elif self.current_db_type == "cassandra":
            self._connect_to_cassandra_search()

    def _connection_failed_cleanup(self):
        if self.client: self.client.close(); self.client = None
        if self.driver: self.driver.close(); self.driver = None
        if self.cassandra_session: self.cassandra_session.shutdown(); self.cassandra_session = None
        if self.cassandra_cluster: self.cassandra_cluster.shutdown(); self.cassandra_cluster = None

        self.connect_btn.setText("Połącz")
        self.search_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._clear_search()

    def _connect_to_mongodb(self):
        connection_string = self.connection_input.text().strip()
        try:
            if self.client: self.client.close()
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.connection_status.setText("Połączono (MongoDB)")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Przełącz")
            self.search_btn.setEnabled(True);
            self.clear_btn.setEnabled(True)
            self._load_databases()
        except ConnectionFailure as e:
            self.connection_status.setText("Błąd połączenia (MongoDB)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd", f"Nie można połączyć z MongoDB:\n{str(e)}")
            self._connection_failed_cleanup()
        except Exception as e:
            self.connection_status.setText("Błąd (MongoDB)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd", f"Wystąpił błąd:\n{str(e)}")
            self._connection_failed_cleanup()

    def _connect_to_neo4j(self):
        uri = self.connection_input.text().strip()
        username = self.neo4j_user_input.text().strip()
        password = self.neo4j_pass_input.text()
        try:
            if self.driver: self.driver.close()
            self.driver = GraphDatabase.driver(uri, auth=(username, password))
            with self.driver.session(database="neo4j") as session:
                session.run("RETURN 1 AS test").single()
            self.connection_status.setText("Połączono (Neo4j)")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Przełącz")
            self.search_btn.setEnabled(True);
            self.clear_btn.setEnabled(True)
            self._load_neo4j_labels()
        except (ServiceUnavailable, AuthError) as e:
            self.connection_status.setText("Błąd połączenia/autoryzacji (Neo4j)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd", f"Nie można połączyć z Neo4j lub błąd autoryzacji:\n{str(e)}")
            self._connection_failed_cleanup()
        except Exception as e:
            self.connection_status.setText("Błąd (Neo4j)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd", f"Wystąpił błąd podczas łączenia z Neo4j:\n{str(e)}")
            self._connection_failed_cleanup()

    def _connect_to_cassandra_search(self):
        contact_points_str = self.connection_input.text().strip()
        username = self.cassandra_user_input_search.text().strip()
        password = self.cassandra_pass_input_search.text()

        if not contact_points_str:
            QMessageBox.warning(self, "Błąd Wejścia", "Contact Points nie mogą być puste.")
            return
        contact_points = [p.strip() for p in contact_points_str.split(',') if p.strip()]
        if not contact_points:
            QMessageBox.warning(self, "Błąd Wejścia", "Nieprawidłowy format Contact Points.")
            return

        auth_provider = PlainTextAuthProvider(username=username, password=password) if username else None
        try:
            if self.cassandra_session: self.cassandra_session.shutdown()
            if self.cassandra_cluster: self.cassandra_cluster.shutdown()

            self.cassandra_cluster = Cluster(contact_points=contact_points, auth_provider=auth_provider,
                                             connect_timeout=10)
            self.cassandra_session = self.cassandra_cluster.connect()

            self.connection_status.setText("Połączono (Cassandra)")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Przełącz")
            self.search_btn.setEnabled(True);
            self.clear_btn.setEnabled(True)
            self._load_cassandra_keyspaces()

        except NoHostAvailable as e:
            self.connection_status.setText("Błąd połączenia (Cassandra)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd", f"Nie można połączyć z Cassandra (NoHostAvailable):\n{str(e)}")
            self._connection_failed_cleanup()
        except Exception as e:
            self.connection_status.setText("Błąd (Cassandra)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Błąd", f"Wystąpił błąd podczas łączenia z Cassandra:\n{str(e)}")
            self._connection_failed_cleanup()

    def _clear_connection(self):
        if self.client: self.client.close(); self.client = None
        if self.driver: self.driver.close(); self.driver = None
        if self.cassandra_session: self.cassandra_session.shutdown(); self.cassandra_session = None
        if self.cassandra_cluster: self.cassandra_cluster.shutdown(); self.cassandra_cluster = None

        self.db_combo.clear()
        self.entity_combo.clear()
        self.field_combo.clear()
        self.connection_status.setText("Niepołączono")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        self.connect_btn.setText("Połącz")
        self.search_btn.setEnabled(False);
        self.clear_btn.setEnabled(False)
        self._clear_search()

    def _load_databases(self):
        if not self.client: return
        self.db_combo.clear()
        try:
            db_names = [db for db in self.client.list_database_names() if db not in ['admin', 'config', 'local']]
            self.db_combo.addItems(sorted(db_names))
        except Exception as e:
            QMessageBox.warning(self, "Ostrzeżenie", f"Nie można załadować baz danych MongoDB:\n{str(e)}")

    def _load_neo4j_labels(self):
        if not self.driver: return
        self.db_combo.clear()
        self.db_combo.addItem("Neo4j Graph")
        self.db_combo.setCurrentIndex(0)
        self.entity_combo.clear()
        try:
            with self.driver.session(database="neo4j") as session:
                result = session.run("CALL db.labels() YIELD label RETURN label")
                labels = sorted([record["label"] for record in result])
                self.entity_combo.addItems(labels)
        except Exception:
            try:
                with self.driver.session(database="neo4j") as session:
                    result = session.run("CALL db.labels()")
                    labels = sorted([record["label"] for record in result])
                    self.entity_combo.addItems(labels)
            except Exception as e2:
                QMessageBox.warning(self, "Ostrzeżenie", f"Nie można załadować etykiet Neo4j:\n{str(e2)}")

    def _load_cassandra_keyspaces(self):
        if not self.cassandra_cluster or not self.cassandra_cluster.metadata: return
        self.db_combo.clear()
        try:
            keyspace_names = list(self.cassandra_cluster.metadata.keyspaces.keys())
            system_keyspaces = {'system', 'system_auth', 'system_distributed', 'system_schema',
                                'system_traces', 'system_views', 'system_virtual_schema',
                                'dse_system', 'dse_auth', 'dse_perf', 'dse_insights', 'dse_insights_local',
                                'solr_admin'}
            user_keyspaces = sorted([ks for ks in keyspace_names if
                                     ks not in system_keyspaces and not ks.startswith("dse_") and not ks.startswith(
                                         "solr_")])
            self.db_combo.addItems(user_keyspaces)
        except Exception as e:
            QMessageBox.warning(self, "Ostrzeżenie", f"Nie można załadować keyspace'ów Cassandra:\n{str(e)}")

    def _update_entities_combo(self, selected_db_name):
        self.entity_combo.clear()
        self.field_combo.clear()
        self.current_db_name = selected_db_name

        if not selected_db_name: return

        if self.current_db_type == "mongodb":
            if not self.client: return
            try:
                db = self.client[selected_db_name]
                self.entity_combo.addItems(sorted(db.list_collection_names()))
            except Exception as e:
                QMessageBox.warning(self, "Ostrzeżenie", f"Nie można załadować kolekcji MongoDB:\n{str(e)}")
        elif self.current_db_type == "neo4j":
            pass
        elif self.current_db_type == "cassandra":
            if not self.cassandra_cluster or not self.cassandra_cluster.metadata: return
            self.current_entity_name = ""
            try:
                keyspace_meta = self.cassandra_cluster.metadata.keyspaces.get(selected_db_name)
                if keyspace_meta:
                    self.entity_combo.addItems(sorted(list(keyspace_meta.tables.keys())))
            except Exception as e:
                QMessageBox.warning(self, "Ostrzeżenie",
                                    f"Nie można załadować tabel Cassandra dla keyspace '{selected_db_name}':\n{str(e)}")

    def _update_search_fields(self, selected_entity_name):
        self.field_combo.clear()
        self.current_entity_name = selected_entity_name
        self._clear_search_inputs_only()

        if not selected_entity_name: return

        if self.current_db_type == "mongodb":
            if not self.client or not self.current_db_name: return
            try:
                db = self.client[self.current_db_name]
                collection = db[selected_entity_name]
                doc = collection.find_one()
                if doc: self.field_combo.addItems(sorted([k for k in doc.keys() if k != "_id"]))
            except Exception as e:
                QMessageBox.warning(self, "Ostrzeżenie",
                                    f"Nie można załadować pól MongoDB dla '{selected_entity_name}':\n{str(e)}")
        elif self.current_db_type == "neo4j":
            if not self.driver: return
            try:
                with self.driver.session(database="neo4j") as session:
                    query = f"MATCH (n:`{selected_entity_name}`) WITH n LIMIT 100 UNWIND keys(n) AS prop RETURN DISTINCT prop ORDER BY prop"
                    result = session.run(query)
                    self.field_combo.addItems([record["prop"] for record in result])
            except Exception as e:
                QMessageBox.warning(self, "Ostrzeżenie",
                                    f"Nie można załadować właściwości Neo4j dla '{selected_entity_name}':\n{str(e)}")
        elif self.current_db_type == "cassandra":
            if not self.cassandra_cluster or not self.cassandra_cluster.metadata or not self.current_db_name: return
            try:
                table_meta = self.cassandra_cluster.metadata.keyspaces[self.current_db_name].tables.get(
                    selected_entity_name)
                if table_meta:
                    self.field_combo.addItems(sorted(list(table_meta.columns.keys())))
            except Exception as e:
                QMessageBox.warning(self, "Ostrzeżenie",
                                    f"Nie można załadować kolumn Cassandra dla '{self.current_db_name}.{selected_entity_name}':\n{str(e)}")

    def _perform_search(self):
        if self.current_db_type == "mongodb":
            self._perform_mongodb_search()
        elif self.current_db_type == "neo4j":
            self._perform_neo4j_search()
        elif self.current_db_type == "cassandra":
            self._perform_cassandra_search()

    def _perform_mongodb_search(self):
        field = self.field_combo.currentText()
        operator = self.operator_combo.currentText()
        value_str = self.value_input.text()
        if not field: QMessageBox.warning(self, "Ostrzeżenie", "Wybierz pole MongoDB."); return
        if not self.client or not self.current_db_name or not self.current_entity_name:
            QMessageBox.critical(self, "Błąd", "MongoDB: Brak połączenia lub wyboru.");
            return
        try:
            db = self.client[self.current_db_name]
            collection = db[self.current_entity_name]
            query_value = self._attempt_type_conversion(value_str)
            query = self._build_mongodb_query(field, operator, query_value)
            results = list(collection.find(query).limit(100))
            count = collection.count_documents(query)
            self._display_results(results, count, "mongodb")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wyszukiwania MongoDB:\n{str(e)}")

    def _perform_neo4j_search(self):
        label = self.current_entity_name
        field = self.field_combo.currentText()
        operator = self.operator_combo.currentText()
        value_str = self.value_input.text()
        if not label: QMessageBox.warning(self, "Ostrzeżenie", "Wybierz etykietę Neo4j."); return
        if not field and not ("istnieje relacja z" in operator): QMessageBox.warning(self, "Ostrzeżenie",
                                                                                     "Wybierz pole Neo4j."); return
        if not self.driver: QMessageBox.critical(self, "Błąd", "Neo4j: Brak połączenia."); return
        try:
            query_value = self._attempt_type_conversion(value_str)
            query, params = self._build_neo4j_query(label, field, operator, query_value)
            neo4j_results = {"nodes": [], "relationships": [], "paths": [], "raw_records": []}
            count = 0
            with self.driver.session(database="neo4j") as session:
                result_cursor = session.run(query, parameters=params)
                record_list = list(result_cursor)
                count = len(record_list)
                for record in record_list:
                    processed_record = False
                    for key_rec in record.keys():
                        val = record[key_rec]
                        if hasattr(val, 'labels') and callable(getattr(val, 'labels')):
                            if val not in neo4j_results["nodes"]: neo4j_results["nodes"].append(
                                val); processed_record = True
                        elif hasattr(val, 'type') and callable(getattr(val, 'type')):
                            if val not in neo4j_results["relationships"]: neo4j_results["relationships"].append(
                                val); processed_record = True
                        elif hasattr(val, 'start_node') and hasattr(val, 'relationships'):
                            if val not in neo4j_results["paths"]: neo4j_results["paths"].append(
                                val); processed_record = True
                    if not processed_record and record not in neo4j_results["raw_records"]:
                        neo4j_results["raw_records"].append(record)
            self._display_results(neo4j_results, count, "neo4j")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wyszukiwania Neo4j:\n{str(e)}")

    def _perform_cassandra_search(self):
        keyspace = self.current_db_name
        table = self.current_entity_name
        field = self.field_combo.currentText()
        operator = self.operator_combo.currentText()
        value_str = self.value_input.text()

        if not keyspace or not table: QMessageBox.warning(self, "Ostrzeżenie",
                                                          "Wybierz keyspace i tabelę Cassandra."); return
        if not field: QMessageBox.warning(self, "Ostrzeżenie", "Wybierz kolumnę Cassandra."); return
        if not self.cassandra_session: QMessageBox.critical(self, "Błąd", "Cassandra: Brak połączenia."); return

        query_string = ""
        params = {}

        try:
            query_value = self._attempt_type_conversion_for_cassandra(value_str, keyspace, table, field)
            query_string, params = self._build_cassandra_query(keyspace, table, field, operator, query_value)
            statement = SimpleStatement(query_string, fetch_size=100)
            rows = list(self.cassandra_session.execute(statement))
            count = len(rows)
            self._display_results(rows, count, "cassandra")

        except InvalidRequest as e:
            QMessageBox.critical(self, "Błąd Zapytania Cassandra",
                                 f"Nieprawidłowe zapytanie CQL:\n{str(e)}\n\nZapytanie: {query_string}\nParametry: {params}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd wyszukiwania Cassandra:\n{str(e)}")

    def _attempt_type_conversion(self, value_str: str) -> Any:
        if value_str.lower() == "true": return True
        if value_str.lower() == "false": return False
        try:
            return int(value_str)
        except ValueError:
            try:
                return float(value_str)
            except ValueError:
                return value_str

    def _attempt_type_conversion_for_cassandra(self, value_str: str, keyspace: str, table: str,
                                               column_name: str) -> Any:
        if self.cassandra_cluster and self.cassandra_cluster.metadata:
            try:
                column_meta = self.cassandra_cluster.metadata.keyspaces[keyspace].tables[table].columns[column_name]
                col_type_name = column_meta.cql_type
                if col_type_name in ['int', 'bigint', 'smallint', 'tinyint', 'varint', 'counter']:
                    return int(value_str)
                elif col_type_name in ['float', 'double', 'decimal']:
                    return float(value_str)
                elif col_type_name == 'boolean':
                    return value_str.lower() == 'true'
                return value_str
            except Exception:
                pass
        return self._attempt_type_conversion(value_str)

    def _build_mongodb_query(self, field, operator, value):
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

    def _build_neo4j_query(self, label, field, operator, value):
        params = {"value": value}
        if "istnieje relacja z" in operator:
            rel_type_str = str(value).strip()
            q = f"MATCH (n:`{label}`)-[r{':`' + rel_type_str + '`' if rel_type_str else ''}]->(m) RETURN n, r, m LIMIT 100"
            return q, {}

        backtick_char = '`'
        double_backtick_char = '``'
        escaped_field_content = field.replace(backtick_char, double_backtick_char)
        safe_field = backtick_char + escaped_field_content + backtick_char

        q_match = f"MATCH (n:`{label}`) "
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

    def _build_cassandra_query(self, keyspace, table, field, operator, value):
        safe_keyspace = '"' + keyspace.replace('"', '""') + '"'
        safe_table = '"' + table.replace('"', '""') + '"'
        safe_field = '"' + field.replace('"', '""') + '"'

        cql_value = ""
        if isinstance(value, str):
            quoted_value = value.replace("'", "''")
            cql_value = f"'{quoted_value}'"
        elif isinstance(value, bool):
            cql_value = str(value).lower()
        else:
            cql_value = str(value)

        query_string = f"SELECT * FROM {safe_keyspace}.{safe_table} "
        params = {}

        if "równa się (=)" in operator:
            query_string += f"WHERE {safe_field} = {cql_value} "

        query_string += "LIMIT 100"

        if "WHERE" in query_string and "ALLOW FILTERING" not in query_string:
            is_pk_component = False
            if self.cassandra_cluster and self.cassandra_cluster.metadata:
                try:
                    table_meta = self.cassandra_cluster.metadata.keyspaces[keyspace].tables[table]
                    pk_components = [col.name for col in table_meta.primary_key]
                    if field in pk_components:
                        is_pk_component = True
                except Exception:
                    pass
            if not is_pk_component:
                query_string += " ALLOW FILTERING"
        return query_string, params

    def _display_results(self, results_data: Any, count: int, db_type: str):
        self.results_tree.clear()
        self.results_count.setText(f"Znaleziono wyników: {count}")

        if db_type == "mongodb":
            self.results_tree.setHeaderLabels(["Pole", "Wartość"])
            for i, doc in enumerate(results_data):
                doc_id = doc.get('_id', f'Dokument {i + 1}')
                doc_item = QTreeWidgetItem([f"Dokument: {doc_id}"])
                self._add_data_to_tree(doc, doc_item, db_type)
                self.results_tree.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)
        elif db_type == "neo4j":
            self.results_tree.setHeaderLabels(["Typ", "Właściwości/Szczegóły"])
            if results_data["nodes"]:
                parent = QTreeWidgetItem(["Węzły"]);
                self.results_tree.addTopLevelItem(parent)
                for node in results_data["nodes"]:
                    item = QTreeWidgetItem([f"Węzeł ({', '.join(node.labels)})", f"id: {node.element_id}"])
                    self._add_data_to_tree(dict(node), item, db_type);
                    parent.addChild(item)
                parent.setExpanded(True)
            if results_data["relationships"]:
                parent = QTreeWidgetItem(["Relacje"]);
                self.results_tree.addTopLevelItem(parent)
                for rel in results_data["relationships"]:
                    item = QTreeWidgetItem([f"Relacja ({rel.type})", f"id: {rel.element_id}"])
                    item.addChild(QTreeWidgetItem(
                        ["Od", f"({', '.join(rel.start_node.labels)}) id: {rel.start_node.element_id}"]))
                    item.addChild(
                        QTreeWidgetItem(["Do", f"({', '.join(rel.end_node.labels)}) id: {rel.end_node.element_id}"]))
                    self._add_data_to_tree(dict(rel), item, db_type);
                    parent.addChild(item)
                parent.setExpanded(True)
            if results_data["paths"]:
                parent = QTreeWidgetItem(["Ścieżki"]);
                self.results_tree.addTopLevelItem(parent)
                for i, path_val in enumerate(results_data["paths"]):
                    item = QTreeWidgetItem([f"Ścieżka {i + 1}", f"Długość: {len(path_val.relationships)}"])
                    parent.addChild(item)
                parent.setExpanded(True)
            if results_data["raw_records"]:
                parent = QTreeWidgetItem(["Inne Wyniki"]);
                self.results_tree.addTopLevelItem(parent)
                for i, record_val in enumerate(results_data["raw_records"]):
                    item = QTreeWidgetItem([f"Rekord {i + 1}"])
                    self._add_data_to_tree(dict(record_val), item, db_type)
                    parent.addChild(item)
                parent.setExpanded(True)
        elif db_type == "cassandra":
            if results_data and isinstance(results_data, list) and len(results_data) > 0 and hasattr(results_data[0],
                                                                                                     '_fields'):
                column_names = results_data[0]._fields
                self.results_tree.setHeaderLabels(column_names)
                for i, row_data in enumerate(results_data):
                    row_values = [str(getattr(row_data, col, 'N/A')) for col in column_names]
                    row_item = QTreeWidgetItem(row_values)
                    self.results_tree.addTopLevelItem(row_item)
            elif results_data:
                self.results_tree.setHeaderLabels(["Wynik Cassandra"])
                self.results_tree.addTopLevelItem(QTreeWidgetItem([str(results_data)]))
            else:
                self.results_tree.setHeaderLabels(["Wyniki Cassandra"])
                self.results_tree.addTopLevelItem(QTreeWidgetItem(["Brak wyników"]))

    def _add_data_to_tree(self, data_item: Any, parent_tree_item: QTreeWidgetItem, db_type: str):
        if isinstance(data_item, dict):
            for key, value in data_item.items():
                if db_type == "mongodb" and key == "_id" and parent_tree_item.text(0).startswith("Dokument:"):
                    continue
                child_node_text = str(key)
                if isinstance(value, dict):
                    child_item = QTreeWidgetItem([child_node_text])
                    self._add_data_to_tree(value, child_item, db_type)
                    parent_tree_item.addChild(child_item)
                elif isinstance(value, list):
                    child_item = QTreeWidgetItem([child_node_text, f"(lista: {len(value)} el.)"])
                    parent_tree_item.addChild(child_item)
                    for i, list_el in enumerate(value):
                        list_el_item = QTreeWidgetItem([f"[{i}]"])
                        self._add_data_to_tree(list_el, list_el_item, db_type)
                        child_item.addChild(list_el_item)
                else:
                    child_value_text = str(value)
                    item = QTreeWidgetItem([child_node_text, child_value_text])
                    parent_tree_item.addChild(item)
        elif db_type == "neo4j":
            if hasattr(data_item, 'labels') and callable(getattr(data_item, 'labels')):
                pass
            elif hasattr(data_item, 'type') and callable(getattr(data_item, 'type')):
                pass
            elif not parent_tree_item.text(1):
                parent_tree_item.setText(1, str(data_item))
        elif not parent_tree_item.text(1):
            parent_tree_item.setText(1, str(data_item))

    def _clear_search_inputs_only(self):
        self.value_input.clear()

    def _clear_search(self):
        self.value_input.clear()
        self.results_tree.clear()
        self.results_count.setText("Znaleziono wyników: 0")
        if self.current_db_type == "mongodb":
            self.results_tree.setHeaderLabels(["Pole", "Wartość"])
        elif self.current_db_type == "neo4j":
            self.results_tree.setHeaderLabels(["Typ", "Właściwości/Szczegóły"])
        elif self.current_db_type == "cassandra":
            self.results_tree.setHeaderLabels(["Kolumna", "Wartość"])


class DatabaseViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Database Data Viewer")
        self.setGeometry(100, 100, 1000, 800)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.mongo_tab = MongoDBTab()
        self.neo4j_tab = Neo4jTab()
        self.cassandra_tab = CassandraTab()
        self.search_tab = SearchTab()
        self.tabs.addTab(self.mongo_tab, "MongoDB")
        self.tabs.addTab(self.neo4j_tab, "Neo4j")
        self.tabs.addTab(self.cassandra_tab, "Cassandra")
        self.tabs.addTab(self.search_tab, "Wyszukaj")


class MongoDBTab(QWidget):
    def __init__(self):
        super().__init__()
        self.connection_string = "mongodb://localhost:27017/"
        self.current_db_name = ""
        self.client = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.connection_input = QLineEdit(self.connection_string)
        connection_layout.addRow("Connection String:", self.connection_input)
        self.connect_btn = QPushButton("Connect to MongoDB")
        self.connect_btn.clicked.connect(self._connect_to_mongodb)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)
        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)
        self.db_combo = QComboBox()
        self.db_combo.setPlaceholderText("Select database")
        self.db_combo.currentTextChanged.connect(self._update_collections_combo)
        selection_layout.addWidget(QLabel("Database:"))
        selection_layout.addWidget(self.db_combo)
        self.collection_combo = QComboBox()
        self.collection_combo.setPlaceholderText("Select collection")
        self.collection_combo.currentTextChanged.connect(self._load_collection_data)
        selection_layout.addWidget(QLabel("Collection:"))
        selection_layout.addWidget(self.collection_combo)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_data)
        self.refresh_btn.setEnabled(False)
        selection_layout.addWidget(self.refresh_btn)
        main_layout.addWidget(selection_panel)
        self.data_tree = QTreeWidget()
        self.data_tree.setHeaderLabels(["Field", "Value"])
        self.data_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.data_tree)
        self.document_count_label = QLabel("Documents: 0")
        main_layout.addWidget(self.document_count_label)

    def _connect_to_mongodb(self):
        connection_string = self.connection_input.text().strip()
        try:
            if self.client: self.client.close()
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect")
            self.refresh_btn.setEnabled(True)
            self._load_databases()
        except ConnectionFailure as e:
            self.connection_status.setText("Connection failed")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", f"Failed to connect to MongoDB:\n{str(e)}")
        except Exception as e:
            self.connection_status.setText("Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

    def _load_databases(self):
        if not self.client: return
        self.db_combo.clear()
        try:
            db_names = self.client.list_database_names()
            self.db_combo.addItems(sorted([name for name in db_names if name not in ['admin', 'config', 'local']]))
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load databases:\n{str(e)}")

    def _update_collections_combo(self, db_name):
        self.collection_combo.clear()
        self.current_db_name = db_name
        if not db_name or not self.client: return
        try:
            db = self.client[db_name]
            collection_names = db.list_collection_names()
            self.collection_combo.addItems(sorted(collection_names))
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load collections:\n{str(e)}")

    def _load_collection_data(self, collection_name):
        self.data_tree.clear()
        if not collection_name or not self.current_db_name or not self.client: return
        try:
            db = self.client[self.current_db_name]
            collection = db[collection_name]
            count = collection.count_documents({})
            self.document_count_label.setText(f"Documents: {count}")
            documents = collection.find().limit(50)
            for doc in documents:
                doc_id_str = str(doc.get('_id', 'N/A'))
                doc_item = QTreeWidgetItem([f"Document {doc_id_str}"])
                self._add_dict_to_tree_mongo(doc, doc_item, is_top_level_doc=True)
                self.data_tree.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load collection data:\n{str(e)}")

    def _add_dict_to_tree_mongo(self, data_dict, parent_item, is_top_level_doc=False):
        for key, value in data_dict.items():
            if is_top_level_doc and key == "_id":
                continue
            if isinstance(value, dict):
                child_item = QTreeWidgetItem([str(key)])
                self._add_dict_to_tree_mongo(value, child_item)
                parent_item.addChild(child_item)
            elif isinstance(value, list):
                list_item_node = QTreeWidgetItem([f"{key} (list)", f"[{len(value)} items]"])
                parent_item.addChild(list_item_node)
                for i, item_in_list in enumerate(value):
                    element_item = QTreeWidgetItem([f"[{i}]"])
                    if isinstance(item_in_list, dict):
                        self._add_dict_to_tree_mongo(item_in_list, element_item)
                    elif isinstance(item_in_list, list):
                        element_item.setText(1, f"(nested list: {len(item_in_list)} items)")
                    else:
                        element_item.setText(1, str(item_in_list))
                    list_item_node.addChild(element_item)
            else:
                item = QTreeWidgetItem([str(key), str(value)])
                parent_item.addChild(item)

    def _refresh_data(self):
        current_collection = self.collection_combo.currentText()
        if current_collection:
            self._load_collection_data(current_collection)


class Neo4jTab(QWidget):
    def __init__(self):
        super().__init__()
        self.uri = "bolt://localhost:7687"
        self.username = "neo4j"
        self.password = ""
        self.driver = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.uri_input = QLineEdit(self.uri)
        connection_layout.addRow("URI:", self.uri_input)
        self.username_input = QLineEdit(self.username)
        connection_layout.addRow("Username:", self.username_input)
        self.password_input = QLineEdit(self.password)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("Password:", self.password_input)
        self.connect_btn = QPushButton("Connect to Neo4j")
        self.connect_btn.clicked.connect(self._connect_to_neo4j)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)
        query_panel = QWidget()
        query_layout = QVBoxLayout(query_panel)
        query_layout.addWidget(QLabel("Cypher Query:"))
        self.query_input = QTextEdit("MATCH (n) RETURN n LIMIT 25")
        self.query_input.setMinimumHeight(100)
        query_layout.addWidget(self.query_input)
        self.execute_btn = QPushButton("Execute Query")
        self.execute_btn.clicked.connect(self._execute_query)
        self.execute_btn.setEnabled(False)
        query_layout.addWidget(self.execute_btn)
        main_layout.addWidget(query_panel)
        samples_panel = QWidget()
        samples_layout = QHBoxLayout(samples_panel)
        samples_layout.addWidget(QLabel("Sample Queries:"))
        self.nodes_btn = QPushButton("All Nodes")
        self.nodes_btn.clicked.connect(lambda: self._set_sample_query("MATCH (n) RETURN n LIMIT 25"))
        self.rels_btn = QPushButton("All Relationships")
        self.rels_btn.clicked.connect(lambda: self._set_sample_query("MATCH ()-[r]->() RETURN r LIMIT 25"))
        self.labels_btn = QPushButton("Node Labels")
        self.labels_btn.clicked.connect(lambda: self._set_sample_query("CALL db.labels() YIELD label RETURN label"))
        self.schema_btn = QPushButton("Schema")
        self.schema_btn.clicked.connect(lambda: self._set_sample_query("CALL db.schema.visualization()"))
        for btn in [self.nodes_btn, self.rels_btn, self.labels_btn, self.schema_btn]:
            btn.setEnabled(False)
            samples_layout.addWidget(btn)
        main_layout.addWidget(samples_panel)
        main_layout.addWidget(QLabel("Results:"))
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Item", "Value"])
        self.results_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.results_tree)
        self.results_count_label = QLabel("Results: 0")
        main_layout.addWidget(self.results_count_label)

    def _connect_to_neo4j(self):
        uri = self.uri_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        try:
            if self.driver: self.driver.close()
            self.driver = GraphDatabase.driver(uri, auth=(username, password))
            with self.driver.session(database="neo4j") as session:
                session.run("RETURN 1").single()
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect")
            for btn in [self.execute_btn, self.nodes_btn, self.rels_btn, self.labels_btn, self.schema_btn]:
                btn.setEnabled(True)
        except (ServiceUnavailable, AuthError) as e:
            self.connection_status.setText("Connection/Auth failed")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", f"Failed to connect or auth error:\n{str(e)}")
        except Exception as e:
            self.connection_status.setText("Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

    def _set_sample_query(self, query):
        self.query_input.setText(query)

    def _execute_query(self):
        self.results_tree.clear()
        query = self.query_input.toPlainText().strip()
        if not query or not self.driver: return
        try:
            with self.driver.session(database="neo4j") as session:
                result_cursor = session.run(query)
                records = list(result_cursor)
                if records and records[0].keys():
                    self.results_tree.setHeaderLabels(records[0].keys())
                elif records:
                    self.results_tree.setHeaderLabels(["Value"])
                else:
                    self.results_tree.setHeaderLabels(["Result"])
                self.results_count_label.setText(f"Results: {len(records)} (Returned by query)")
                for i, record in enumerate(records):
                    if len(record.keys()) == 1:
                        key = record.keys()[0]
                        record_item_text = f"Record {i + 1}"
                        if key and key != record[key]:
                            record_item_text += f": {key}"
                        item = QTreeWidgetItem([record_item_text])
                        self._add_neo4j_value_to_tree(record[key], item, is_direct_value=True)
                    else:
                        item = QTreeWidgetItem([f"Record {i + 1}"])
                        for key in record.keys():
                            sub_item = QTreeWidgetItem([key])
                            self._add_neo4j_value_to_tree(record[key], sub_item)
                            item.addChild(sub_item)
                    self.results_tree.addTopLevelItem(item)
                    if len(record.keys()) > 1:
                        item.setExpanded(True)
        except Exception as e:
            QMessageBox.warning(self, "Query Error", f"Error executing query:\n{str(e)}")
            self.results_count_label.setText("Results: 0")
            self.results_tree.setHeaderLabels(["Error"])
            self.results_tree.addTopLevelItem(QTreeWidgetItem([f"Query failed: {str(e)}"]))

    def _add_neo4j_value_to_tree(self, value, parent_item: QTreeWidgetItem, is_direct_value=False):
        text_for_value_column = ""
        children_to_add = []
        if hasattr(value, 'labels') and callable(getattr(value, 'labels')):
            labels = ", ".join(value.labels)
            text_for_value_column = f"Node ({labels}) id: {value.element_id}"
            props_item = QTreeWidgetItem(["properties"])
            for k, v_prop in dict(value).items():
                prop_item = QTreeWidgetItem([str(k)])
                self._add_neo4j_value_to_tree(v_prop, prop_item)
                props_item.addChild(prop_item)
            if props_item.childCount() > 0: children_to_add.append(props_item)
        elif hasattr(value, 'type') and callable(getattr(value, 'type')):
            text_for_value_column = f"Relationship ({value.type}) id: {value.element_id}"
            start_info = f"Start: ({', '.join(value.start_node.labels)}) id: {value.start_node.element_id}"
            end_info = f"End: ({', '.join(value.end_node.labels)}) id: {value.end_node.element_id}"
            children_to_add.append(QTreeWidgetItem(["from", start_info]))
            children_to_add.append(QTreeWidgetItem(["to", end_info]))
            props_item = QTreeWidgetItem(["properties"])
            for k, v_prop in dict(value).items():
                prop_item = QTreeWidgetItem([str(k)])
                self._add_neo4j_value_to_tree(v_prop, prop_item)
                props_item.addChild(prop_item)
            if props_item.childCount() > 0: children_to_add.append(props_item)
        elif hasattr(value, 'start_node') and hasattr(value, 'relationships'):
            text_for_value_column = f"Path (length: {len(value.relationships)})"
            nodes_item = QTreeWidgetItem(["nodes"])
            for i, node_in_path in enumerate(value.nodes):
                node_item = QTreeWidgetItem([f"[{i}]"])
                self._add_neo4j_value_to_tree(node_in_path, node_item)
                nodes_item.addChild(node_item)
            if nodes_item.childCount() > 0: children_to_add.append(nodes_item)
            rels_item = QTreeWidgetItem(["relationships"])
            for i, rel_in_path in enumerate(value.relationships):
                rel_item = QTreeWidgetItem([f"[{i}]"])
                self._add_neo4j_value_to_tree(rel_in_path, rel_item)
                rels_item.addChild(rel_item)
            if rels_item.childCount() > 0: children_to_add.append(rels_item)
        elif isinstance(value, dict):
            text_for_value_column = "Map (Dictionary)"
            for k_dict, v_dict in value.items():
                dict_child_item = QTreeWidgetItem([str(k_dict)])
                self._add_neo4j_value_to_tree(v_dict, dict_child_item)
                children_to_add.append(dict_child_item)
        elif isinstance(value, list):
            text_for_value_column = f"List [{len(value)} items]"
            for i_list, v_list_item in enumerate(value):
                list_child_item = QTreeWidgetItem([f"[{i_list}]"])
                self._add_neo4j_value_to_tree(v_list_item, list_child_item)
                children_to_add.append(list_child_item)
        else:
            text_for_value_column = str(value)
        if is_direct_value:
            parent_item.setText(1, text_for_value_column)
        elif parent_item.text(1) == "":
            parent_item.setText(1, text_for_value_column)
        if children_to_add:
            parent_item.addChildren(children_to_add)
            parent_item.setExpanded(True)


class CassandraTab(QWidget):
    def __init__(self):
        super().__init__()
        self.contact_points_str = "127.0.0.1"
        self.username = ""
        self.password = ""
        self.cluster = None
        self.session = None
        self.current_keyspace = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)
        self.contact_points_input = QLineEdit(self.contact_points_str)
        connection_layout.addRow("Contact Points:", self.contact_points_input)
        self.username_input = QLineEdit(self.username)
        self.username_input.setPlaceholderText("(Optional)")
        connection_layout.addRow("Username:", self.username_input)
        self.password_input = QLineEdit(self.password)
        self.password_input.setPlaceholderText("(Optional)")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("Password:", self.password_input)
        self.connect_btn = QPushButton("Connect to Cassandra")
        self.connect_btn.clicked.connect(self._connect_to_cassandra)
        connection_layout.addRow(self.connect_btn)
        self.connection_status = QLabel("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)
        main_layout.addWidget(connection_panel)
        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)
        self.keyspace_combo = QComboBox()
        self.keyspace_combo.setPlaceholderText("Select keyspace")
        self.keyspace_combo.currentTextChanged.connect(self._update_tables_combo)
        self.keyspace_combo.setEnabled(False)
        selection_layout.addWidget(QLabel("Keyspace:"))
        selection_layout.addWidget(self.keyspace_combo)
        self.table_combo = QComboBox()
        self.table_combo.setPlaceholderText("Select table")
        self.table_combo.currentTextChanged.connect(self._load_table_data)
        self.table_combo.setEnabled(False)
        selection_layout.addWidget(QLabel("Table:"))
        selection_layout.addWidget(self.table_combo)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_data)
        self.refresh_btn.setEnabled(False)
        selection_layout.addWidget(self.refresh_btn)
        main_layout.addWidget(selection_panel)
        self.data_tree = QTreeWidget()
        self.data_tree.setColumnCount(1)
        self.data_tree.setHeaderLabels(["Row Data"])
        main_layout.addWidget(self.data_tree)
        self.row_count_label = QLabel("Rows: 0")
        main_layout.addWidget(self.row_count_label)

    def _connect_to_cassandra(self):
        contact_points_str = self.contact_points_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not contact_points_str:
            QMessageBox.warning(self, "Input Error", "Contact Points cannot be empty.")
            return
        contact_points = [p.strip() for p in contact_points_str.split(',') if p.strip()]
        if not contact_points:
            QMessageBox.warning(self, "Input Error", "Invalid Contact Points format.")
            return
        auth_provider = PlainTextAuthProvider(username=username, password=password) if username else None
        try:
            if self.session: self.session.shutdown()
            if self.cluster: self.cluster.shutdown()
            self.cluster = Cluster(contact_points=contact_points, auth_provider=auth_provider,
                                   connect_timeout=10)
            self.session = self.cluster.connect()
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect")
            self.refresh_btn.setEnabled(True)
            self.keyspace_combo.setEnabled(True)
            self.table_combo.setEnabled(True)
            self._load_keyspaces()
        except NoHostAvailable as e:
            self.connection_status.setText("Connection failed (NoHostAvailable)")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error",
                                 f"Failed to connect to Cassandra (NoHostAvailable):\n{str(e)}")
            self._reset_ui_on_disconnect()
        except Exception as e:
            self.connection_status.setText("Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Error", f"An error occurred during connection:\n{str(e)}")
            self._reset_ui_on_disconnect()

    def _reset_ui_on_disconnect(self):
        self.cluster = None;
        self.session = None;
        self.current_keyspace = None
        self.connection_status.setText("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        self.connect_btn.setText("Connect to Cassandra")
        self.keyspace_combo.clear();
        self.table_combo.clear();
        self.data_tree.clear()
        self.row_count_label.setText("Rows: 0")
        for W in [self.refresh_btn, self.keyspace_combo, self.table_combo]: W.setEnabled(False)
        self.data_tree.setColumnCount(1);
        self.data_tree.setHeaderLabels(["Row Data"])

    def _load_keyspaces(self):
        if not self.cluster or not self.cluster.metadata: return
        self.keyspace_combo.clear();
        self.table_combo.clear()
        try:
            keyspace_names = list(self.cluster.metadata.keyspaces.keys())
            system_keyspaces = {'system', 'system_auth', 'system_distributed', 'system_schema',
                                'system_traces', 'system_views', 'system_virtual_schema',
                                'dse_system', 'dse_auth', 'dse_perf', 'dse_insights', 'dse_insights_local',
                                'solr_admin'}
            user_keyspaces = sorted([ks for ks in keyspace_names if
                                     ks not in system_keyspaces and not ks.startswith("dse_") and not ks.startswith(
                                         "solr_")])
            self.keyspace_combo.addItems(user_keyspaces)
            self.keyspace_combo.setCurrentIndex(-1)
            self.keyspace_combo.setPlaceholderText("Select keyspace")
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load keyspaces:\n{str(e)}")

    def _update_tables_combo(self, keyspace_name):
        self.table_combo.clear();
        self.data_tree.clear()
        self.row_count_label.setText("Rows: 0")
        self.current_keyspace = keyspace_name
        if not keyspace_name or not self.cluster or not self.cluster.metadata:
            self.table_combo.setPlaceholderText("Select table")
            return
        try:
            tables_metadata = self.cluster.metadata.keyspaces.get(keyspace_name)
            if tables_metadata:
                table_names = sorted(list(tables_metadata.tables.keys()))
                self.table_combo.addItems(table_names)
                self.table_combo.setCurrentIndex(-1)
                self.table_combo.setPlaceholderText("Select table")
            else:
                self.table_combo.setPlaceholderText("(No tables found)")
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load tables for '{keyspace_name}':\n{str(e)}")
            self.table_combo.setPlaceholderText("(Error loading tables)")

    def _load_table_data(self, table_name):
        self.data_tree.clear()
        self.row_count_label.setText("Rows: 0")
        if not table_name or not self.current_keyspace or not self.session:
            self.data_tree.setColumnCount(1);
            self.data_tree.setHeaderLabels(["Row Data"])
            return
        try:
            self.session.set_keyspace(self.current_keyspace)
            query = f"SELECT * FROM \"{self.current_keyspace}\".\"{table_name}\" LIMIT 100"
            statement = SimpleStatement(query, fetch_size=50)
            result_set = self.session.execute(statement)
            rows = list(result_set)
            self.row_count_label.setText(f"Rows: {len(rows)} (limited to 100)")
            if rows:
                column_names = rows[0]._fields
                self.data_tree.setColumnCount(len(column_names))
                self.data_tree.setHeaderLabels(column_names)
                for row in rows:
                    row_values = [str(getattr(row, col, 'N/A')) for col in column_names]
                    self.data_tree.addTopLevelItem(QTreeWidgetItem(row_values))
                for i in range(len(column_names)): self.data_tree.resizeColumnToContents(i)
            else:
                self.data_tree.setColumnCount(1)
                self.data_tree.setHeaderLabels([f"No data found in {table_name}"])
        except InvalidRequest as e:
            QMessageBox.warning(self, "Query Error", f"Invalid CQL for '{table_name}':\n{str(e)}")
            self.data_tree.setColumnCount(1);
            self.data_tree.setHeaderLabels(["Query Error"])
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load data from '{table_name}':\n{str(e)}")
            self.data_tree.setColumnCount(1);
            self.data_tree.setHeaderLabels(["Error Loading Data"])

    def _refresh_data(self):
        current_keyspace = self.keyspace_combo.currentText()
        if self.cluster:
            self._load_keyspaces()
            if current_keyspace:
                keyspace_idx = self.keyspace_combo.findText(current_keyspace)
                if keyspace_idx != -1:
                    self.keyspace_combo.setCurrentIndex(keyspace_idx)
                else:
                    self.keyspace_combo.setCurrentIndex(-1)
                    self.table_combo.clear()
                    self.data_tree.clear()
                    self.row_count_label.setText("Rows: 0")
            else:
                self.table_combo.clear()
                self.data_tree.clear()
                self.row_count_label.setText("Rows: 0")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DatabaseViewerApp()
    window.show()
    sys.exit(app.exec())