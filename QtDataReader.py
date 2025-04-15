import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QLineEdit, QFormLayout, QScrollArea, QTabWidget,
    QTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.uic.properties import QtGui
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement
from cassandra import InvalidRequest


class DatabaseViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Database Data Viewer")
        self.setGeometry(100, 100, 1000, 700)

        # Main tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create MongoDB tab
        self.mongo_tab = MongoDBTab()
        self.tabs.addTab(self.mongo_tab, "MongoDB")

        # Create Neo4j tab
        self.neo4j_tab = Neo4jTab()
        self.tabs.addTab(self.neo4j_tab, "Neo4j")

        # Create Cassandra tab
        self.cassandra_tab = CassandraTab()
        self.tabs.addTab(self.cassandra_tab, "Cassandra")


class MongoDBTab(QWidget):
    def __init__(self):
        super().__init__()

        # MongoDB connection settings
        self.connection_string = "mongodb://localhost:27017/"
        self.current_db_name = ""
        self.client = None

        self._setup_ui()

    def _setup_ui(self):
        """Configure the MongoDB tab interface."""
        main_layout = QVBoxLayout(self)

        # --- Connection Panel ---
        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)

        # Connection string input
        self.connection_input = QLineEdit(self.connection_string)
        connection_layout.addRow("Connection String:", self.connection_input)

        # Connect button
        self.connect_btn = QPushButton("Connect to MongoDB")
        self.connect_btn.clicked.connect(self._connect_to_mongodb)
        connection_layout.addRow(self.connect_btn)

        # Status label
        self.connection_status = QLabel("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)

        main_layout.addWidget(connection_panel)

        # --- Database/Collection Selection ---
        selection_panel = QWidget()
        selection_layout = QHBoxLayout(selection_panel)

        # Database selection
        self.db_combo = QComboBox()
        self.db_combo.setPlaceholderText("Select database")
        self.db_combo.currentTextChanged.connect(self._update_collections_combo)
        selection_layout.addWidget(QLabel("Database:"))
        selection_layout.addWidget(self.db_combo)

        # Collection selection
        self.collection_combo = QComboBox()
        self.collection_combo.setPlaceholderText("Select collection")
        self.collection_combo.currentTextChanged.connect(self._load_collection_data)
        selection_layout.addWidget(QLabel("Collection:"))
        selection_layout.addWidget(self.collection_combo)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_data)
        self.refresh_btn.setEnabled(False)
        selection_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(selection_panel)

        # --- Data Display ---
        self.data_tree = QTreeWidget()
        self.data_tree.setHeaderLabels(["Field", "Value"])
        self.data_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.data_tree)

        # --- Document Count ---
        self.document_count_label = QLabel("Documents: 0")
        main_layout.addWidget(self.document_count_label)

    def _connect_to_mongodb(self):
        """Establish connection to MongoDB."""
        connection_string = self.connection_input.text().strip()

        try:
            # Close existing connection if any
            if self.client:
                self.client.close()

            self.client = MongoClient(connection_string)

            # Test the connection
            self.client.admin.command('ping')

            # Update UI
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect")
            self.refresh_btn.setEnabled(True)

            # Load databases
            self._load_databases()

        except ConnectionFailure as e:
            self.connection_status.setText(f"Connection failed: {str(e)}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", f"Failed to connect to MongoDB:\n{str(e)}")
        except Exception as e:
            self.connection_status.setText(f"Error: {str(e)}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

    def _load_databases(self):
        """Load available databases into the combo box."""
        if not self.client:
            return

        self.db_combo.clear()

        try:
            db_names = self.client.list_database_names()
            self.db_combo.addItems(sorted(db_names))
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load databases:\n{str(e)}")

    def _update_collections_combo(self, db_name):
        """Update collections combo when database changes."""
        self.collection_combo.clear()
        self.current_db_name = db_name

        if not db_name or not self.client:
            return

        try:
            db = self.client[db_name]
            collection_names = db.list_collection_names()
            self.collection_combo.addItems(sorted(collection_names))
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load collections:\n{str(e)}")

    def _load_collection_data(self, collection_name):
        """Load data from the selected collection."""
        self.data_tree.clear()

        if not collection_name or not self.current_db_name or not self.client:
            return

        try:
            db = self.client[self.current_db_name]
            collection = db[collection_name]

            # Get document count
            count = collection.count_documents({})
            self.document_count_label.setText(f"Documents: {count}")

            # Get first few documents to display
            documents = collection.find().limit(50)

            for doc in documents:
                doc_item = QTreeWidgetItem([f"Document {doc.get('_id', '')}"])
                self._add_dict_to_tree(doc, doc_item)
                self.data_tree.addTopLevelItem(doc_item)
                doc_item.setExpanded(True)

        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load collection data:\n{str(e)}")

    def _add_dict_to_tree(self, data, parent_item):
        """Recursively add dictionary data to the tree widget."""
        if not isinstance(data, dict):
            return

        for key, value in data.items():
            if key == "_id":
                continue  # Skip _id as it's already in the parent

            if isinstance(value, dict):
                child_item = QTreeWidgetItem([str(key)])
                self._add_dict_to_tree(value, child_item)
                parent_item.addChild(child_item)
            elif isinstance(value, list):
                child_item = QTreeWidgetItem([f"{key} (list)"])
                for i, item in enumerate(value):
                    list_item = QTreeWidgetItem([f"[{i}]"])
                    if isinstance(item, dict):
                        self._add_dict_to_tree(item, list_item)
                    else:
                        list_item.setText(1, str(item))
                    child_item.addChild(list_item)
                parent_item.addChild(child_item)
            else:
                item = QTreeWidgetItem([str(key), str(value)])
                parent_item.addChild(item)

    def _refresh_data(self):
        """Refresh the currently viewed data."""
        current_collection = self.collection_combo.currentText()
        if current_collection:
            self._load_collection_data(current_collection)


class Neo4jTab(QWidget):
    def __init__(self):
        super().__init__()

        # Neo4j connection settings
        self.uri = "bolt://localhost:7687"
        self.username = "neo4j"
        self.password = ""
        self.driver = None

        self._setup_ui()

    def _setup_ui(self):
        """Configure the Neo4j tab interface."""
        main_layout = QVBoxLayout(self)

        # --- Connection Panel ---
        connection_panel = QWidget()
        connection_layout = QFormLayout(connection_panel)

        # URI input
        self.uri_input = QLineEdit(self.uri)
        connection_layout.addRow("URI:", self.uri_input)

        # Username input
        self.username_input = QLineEdit(self.username)
        connection_layout.addRow("Username:", self.username_input)

        # Password input
        self.password_input = QLineEdit(self.password)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("Password:", self.password_input)

        # Connect button
        self.connect_btn = QPushButton("Connect to Neo4j")
        self.connect_btn.clicked.connect(self._connect_to_neo4j)
        connection_layout.addRow(self.connect_btn)

        # Status label
        self.connection_status = QLabel("Not connected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addRow("Status:", self.connection_status)

        main_layout.addWidget(connection_panel)

        # --- Query Panel ---
        query_panel = QWidget()
        query_layout = QVBoxLayout(query_panel)

        query_layout.addWidget(QLabel("Cypher Query:"))

        # Query text area
        self.query_input = QTextEdit()
        self.query_input.setPlaceholderText("MATCH (n) RETURN n LIMIT 25")
        self.query_input.setMinimumHeight(100)
        query_layout.addWidget(self.query_input)

        # Execute button
        self.execute_btn = QPushButton("Execute Query")
        self.execute_btn.clicked.connect(self._execute_query)
        self.execute_btn.setEnabled(False)
        query_layout.addWidget(self.execute_btn)

        main_layout.addWidget(query_panel)

        # --- Sample Queries ---
        samples_panel = QWidget()
        samples_layout = QHBoxLayout(samples_panel)

        # Sample query buttons
        samples_layout.addWidget(QLabel("Sample Queries:"))

        self.nodes_btn = QPushButton("All Nodes")
        self.nodes_btn.clicked.connect(lambda: self._set_sample_query("MATCH (n) RETURN n LIMIT 25"))
        self.nodes_btn.setEnabled(False)
        samples_layout.addWidget(self.nodes_btn)

        self.rels_btn = QPushButton("All Relationships")
        self.rels_btn.clicked.connect(lambda: self._set_sample_query("MATCH ()-[r]->() RETURN r LIMIT 25"))
        self.rels_btn.setEnabled(False)
        samples_layout.addWidget(self.rels_btn)

        self.labels_btn = QPushButton("Node Labels")
        self.labels_btn.clicked.connect(lambda: self._set_sample_query("CALL db.labels()"))
        self.labels_btn.setEnabled(False)
        samples_layout.addWidget(self.labels_btn)

        self.schema_btn = QPushButton("Schema")
        self.schema_btn.clicked.connect(lambda: self._set_sample_query("CALL db.schema.visualization()"))
        self.schema_btn.setEnabled(False)
        samples_layout.addWidget(self.schema_btn)

        main_layout.addWidget(samples_panel)

        # --- Results Display ---
        main_layout.addWidget(QLabel("Results:"))

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Item", "Value"])
        self.results_tree.setColumnWidth(0, 300)
        main_layout.addWidget(self.results_tree)

        # --- Results Count ---
        self.results_count_label = QLabel("Results: 0")
        main_layout.addWidget(self.results_count_label)

    def _connect_to_neo4j(self):
        """Establish connection to Neo4j."""
        uri = self.uri_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        try:
            # Close existing connection if any
            if self.driver:
                self.driver.close()

            # Create new driver
            self.driver = GraphDatabase.driver(uri, auth=(username, password))

            # Test the connection
            with self.driver.session() as session:
                result = session.run("RETURN 1 AS test")
                result.single()

            # Update UI
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Reconnect")
            self.execute_btn.setEnabled(True)
            self.nodes_btn.setEnabled(True)
            self.rels_btn.setEnabled(True)
            self.labels_btn.setEnabled(True)
            self.schema_btn.setEnabled(True)

        except ServiceUnavailable as e:
            self.connection_status.setText(f"Connection failed: {str(e)}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Connection Error", f"Failed to connect to Neo4j:\n{str(e)}")
        except Exception as e:
            self.connection_status.setText(f"Error: {str(e)}")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

    def _set_sample_query(self, query):
        """Set a sample query in the query input."""
        self.query_input.setText(query)

    def _execute_query(self):
        """Execute the Cypher query and display results."""
        self.results_tree.clear()
        query = self.query_input.toPlainText().strip()

        if not query or not self.driver:
            return

        try:
            with self.driver.session() as session:
                result = session.run(query)

                # Process results
                records = list(result)
                self.results_count_label.setText(f"Results: {len(records)}")

                # Get column keys
                if records:
                    keys = records[0].keys()

                    # Add results to tree
                    for i, record in enumerate(records):
                        record_item = QTreeWidgetItem([f"Record {i + 1}"])

                        for key in keys:
                            value = record[key]
                            key_item = QTreeWidgetItem([key])
                            self._add_neo4j_value_to_tree(value, key_item)
                            record_item.addChild(key_item)

                        self.results_tree.addTopLevelItem(record_item)
                        record_item.setExpanded(True)

        except Exception as e:
            QMessageBox.warning(self, "Query Error", f"Error executing query:\n{str(e)}")

    def _add_neo4j_value_to_tree(self, value, parent_item):
        """Add Neo4j value to tree, handling nodes and relationships."""
        # Handle Neo4j Node
        if hasattr(value, 'labels') and callable(getattr(value, 'labels')):
            # It's a Node
            labels = ", ".join(value.labels)
            parent_item.setText(1, f"Node ({labels})")

            # Add ID
            if hasattr(value, 'id'):
                id_item = QTreeWidgetItem(["id", str(value.id)])
                parent_item.addChild(id_item)

            # Add properties
            props_item = QTreeWidgetItem(["properties"])
            for key, prop_value in dict(value).items():
                prop_item = QTreeWidgetItem([key, str(prop_value)])
                props_item.addChild(prop_item)
            parent_item.addChild(props_item)

        # Handle Neo4j Relationship
        elif hasattr(value, 'type') and callable(getattr(value, 'type')):
            # It's a Relationship
            parent_item.setText(1, f"Relationship ({value.type})")

            # Add ID
            if hasattr(value, 'id'):
                id_item = QTreeWidgetItem(["id", str(value.id)])
                parent_item.addChild(id_item)

            # Add start and end nodes
            if hasattr(value, 'start_node') and hasattr(value, 'end_node'):
                start_labels = ", ".join(value.start_node.labels)
                end_labels = ", ".join(value.end_node.labels)

                start_item = QTreeWidgetItem(["start_node", f"Node ({start_labels}) id={value.start_node.id}"])
                parent_item.addChild(start_item)

                end_item = QTreeWidgetItem(["end_node", f"Node ({end_labels}) id={value.end_node.id}"])
                parent_item.addChild(end_item)

            # Add properties
            props_item = QTreeWidgetItem(["properties"])
            for key, prop_value in dict(value).items():
                prop_item = QTreeWidgetItem([key, str(prop_value)])
                props_item.addChild(prop_item)
            parent_item.addChild(props_item)

        # Handle Path
        elif hasattr(value, 'start_node') and hasattr(value, 'relationships'):
            # It's a Path
            parent_item.setText(1, f"Path (length: {len(value.relationships)})")

            # Add nodes and relationships
            nodes_item = QTreeWidgetItem(["nodes"])
            for i, node in enumerate(value.nodes):
                node_item = QTreeWidgetItem([f"[{i}]"])
                self._add_neo4j_value_to_tree(node, node_item)
                nodes_item.addChild(node_item)
            parent_item.addChild(nodes_item)

            rels_item = QTreeWidgetItem(["relationships"])
            for i, rel in enumerate(value.relationships):
                rel_item = QTreeWidgetItem([f"[{i}]"])
                self._add_neo4j_value_to_tree(rel, rel_item)
                rels_item.addChild(rel_item)
            parent_item.addChild(rels_item)

        # Handle dictionaries (like properties)
        elif isinstance(value, dict):
            for key, dict_value in value.items():
                child_item = QTreeWidgetItem([str(key)])
                if isinstance(dict_value, (dict, list)) or hasattr(dict_value, 'labels'):
                    self._add_neo4j_value_to_tree(dict_value, child_item)
                else:
                    child_item.setText(1, str(dict_value))
                parent_item.addChild(child_item)

        # Handle lists
        elif isinstance(value, list):
            for i, item in enumerate(value):
                list_item = QTreeWidgetItem([f"[{i}]"])
                if isinstance(item, (dict, list)) or hasattr(item, 'labels'):
                    self._add_neo4j_value_to_tree(item, list_item)
                else:
                    list_item.setText(1, str(item))
                parent_item.addChild(list_item)

        # Simple values
        else:
            parent_item.setText(1, str(value))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DatabaseViewerApp()
    window.show()
    sys.exit(app.exec())