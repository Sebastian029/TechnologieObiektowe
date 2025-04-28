import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QTextEdit, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt

from MongoDB.main import PyMongoConverter  # Zakładam, że masz ten plik w tym samym katalogu
from Neo4j.main import Neo4jConverter  # Zakładam, że masz ten plik w tym samym katalogu

class UniversalConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        # Inicjalizacja konwerterów (używamy Twoich klas bez zmian)
        self.mongo_converter = PyMongoConverter()
        self.neo4j_converter = Neo4jConverter()
    
    def init_ui(self):
        self.setWindowTitle("Universal Database Converter")
        self.setFixedSize(800, 600)
        
        layout = QVBoxLayout()
        
        # Sekcja kodu klasy
        layout.addWidget(QLabel("Class Code:"))
        self.class_code_edit = QTextEdit()
        self.class_code_edit.setPlaceholderText("Paste your class definition here...")
        layout.addWidget(self.class_code_edit)
        
        # Sekcja obiektów
        layout.addWidget(QLabel("Objects Code (objects_list):"))
        self.objects_code_edit = QTextEdit()
        self.objects_code_edit.setPlaceholderText("Paste your objects_list definition here...")
        layout.addWidget(self.objects_code_edit)
        
        # Przyciski akcji
        button_layout = QHBoxLayout()
        
        self.mongo_button = QPushButton("Save to MongoDB")
        self.mongo_button.clicked.connect(self.save_to_mongo)
        button_layout.addWidget(self.mongo_button)
        
        self.neo4j_button = QPushButton("Save to Neo4j")
        self.neo4j_button.clicked.connect(self.save_to_neo4j)
        button_layout.addWidget(self.neo4j_button)
        
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_inputs)
        button_layout.addWidget(self.clear_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def execute_code(self):
        """Wykonuje kod i zwraca objects_list"""
        local_vars = {}
        try:
            # Wykonaj kod klasy
            exec(self.class_code_edit.toPlainText(), globals(), local_vars)
            # Wykonaj kod obiektów
            exec(self.objects_code_edit.toPlainText(), globals(), local_vars)
            
            if 'objects_list' not in local_vars:
                raise ValueError("objects_list not found in the provided code")
                
            return local_vars['objects_list']
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Code execution failed:\n{str(e)}")
            return None
    
    def save_to_mongo(self):
        objects = self.execute_code()
        if objects:
            try:
                for obj in objects:
                    self.mongo_converter.save_to_mongodb(obj)
                QMessageBox.information(self, "Success", "Objects saved to MongoDB!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"MongoDB save failed:\n{str(e)}")
    
    def save_to_neo4j(self):
        objects = self.execute_code()
        if objects:
            try:
                for obj in objects:
                    self.neo4j_converter.save(obj)
                QMessageBox.information(self, "Success", "Objects saved to Neo4j!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Neo4j save failed:\n{str(e)}")
    
    def clear_inputs(self):
        self.class_code_edit.clear()
        self.objects_code_edit.clear()
    
    def closeEvent(self, event):
        """Zamyka połączenia przy zamykaniu aplikacji"""
        self.mongo_converter.close()
        self.neo4j_converter.close()
        event.accept()

# Tutaj wklej swoje oryginalne klasy PyMongoConverter i Neo4jConverter
# (bez żadnych zmian, dokładnie tak jak je podałeś)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UniversalConverterApp()
    window.show()
    sys.exit(app.exec())