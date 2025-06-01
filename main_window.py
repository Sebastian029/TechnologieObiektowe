import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QTextEdit, QPushButton, QMessageBox)
from MongoDB.main import PyMongoConverter  
from Neo4j.main import Neo4jConverter  
from Cassandra.main import PyCassandraConverter

class UniversalConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        self.mongo_converter = PyMongoConverter()
        self.neo4j_converter = Neo4jConverter()
        self.cassandra_converter = PyCassandraConverter()
    
    def init_ui(self):
        self.setWindowTitle("Database Converter")
        self.setFixedSize(800, 600)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Class Code:"))
        self.class_code_edit = QTextEdit()
        self.class_code_edit.setPlaceholderText("Class definitions")
        layout.addWidget(self.class_code_edit)
        
        layout.addWidget(QLabel("Objects Code:"))
        self.objects_code_edit = QTextEdit()
        self.objects_code_edit.setPlaceholderText("Objects definitions")
        layout.addWidget(self.objects_code_edit)
        
        button_layout = QHBoxLayout()
        
        self.mongo_button = QPushButton("Save to MongoDB")
        self.mongo_button.clicked.connect(self.save_to_mongo)
        button_layout.addWidget(self.mongo_button)
        
        self.neo4j_button = QPushButton("Save to Neo4j")
        self.neo4j_button.clicked.connect(self.save_to_neo4j)
        button_layout.addWidget(self.neo4j_button)

        self.cassandra_button = QPushButton("Save to Cassandra")
        self.cassandra_button.clicked.connect(self.save_to_casandra)
        button_layout.addWidget(self.cassandra_button)
        
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_inputs)
        button_layout.addWidget(self.clear_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def get_objects(self):
        namespace = {}
        try:
            # Połącz oba kody w jeden string
            full_code = self.class_code_edit.toPlainText() + "\n" + self.objects_code_edit.toPlainText()
            exec(full_code, namespace)

            # Lub wykonaj oba w tym samym namespace (Twoja obecna metoda powinna działać)
            # exec(self.class_code_edit.toPlainText(), namespace)
            # exec(self.objects_code_edit.toPlainText(), namespace)

            objects = []
            class_names = [name for name, obj in namespace.items()
                           if isinstance(obj, type) and not name.startswith('__')]

            for var_name, var_value in namespace.items():
                if var_name.startswith('__') or var_name in class_names:
                    continue

                if isinstance(var_value, list):
                    if var_value and any(
                            isinstance(x, tuple(namespace[cls] for cls in class_names)) for x in var_value):
                        objects.extend(var_value)
                elif any(isinstance(var_value, namespace[cls]) for cls in class_names):
                    objects.append(var_value)

            if not objects:
                raise ValueError("No objects found in the provided code.")

            return objects

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Code execution failed:\n{str(e)}")
            return None

    def save_to_mongo(self):
        objects = self.get_objects()
        if objects:
            try:
                for obj in objects:
                    self.mongo_converter.save_to_mongodb(obj)
                QMessageBox.information(self, "Success", f"Saved {len(objects)} objects to MongoDB!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"MongoDB save failed:\n{str(e)}")
    
    def save_to_neo4j(self):
        objects = self.get_objects()
        if objects:
            try:
                for obj in objects:
                    self.neo4j_converter.save(obj)
                QMessageBox.information(self, "Success", f"Saved {len(objects)} objects to Neo4j!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Neo4j save failed:\n{str(e)}")

    def save_to_casandra(self):
        objects = self.get_objects()
        if objects:
            try:
                for obj in objects:
                    self.cassandra_converter.save_to_cassandra(obj)
                QMessageBox.information(self, "Success", f"Saved {len(objects)} objects to Cassandra!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cassandra save failed:\n{str(e)}")
    
    def clear_inputs(self):
        self.class_code_edit.clear()
        self.objects_code_edit.clear()
        
    
    def closeEvent(self, event):
        self.mongo_converter.close()
        self.neo4j_converter.close()
        self.cassandra_converter.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UniversalConverterApp()
    window.show()
    sys.exit(app.exec())