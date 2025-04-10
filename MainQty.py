import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                             QComboBox, QMessageBox, QTreeWidget, QTreeWidgetItem)
from PyQt6.QtCore import Qt

class ClassDiagramEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Edytor Diagramów Klas")
        self.setGeometry(100, 100, 1000, 700)
        
        # Dane aplikacji
        self.classes = {}  # Słownik przechowujący klasy: {nazwa: {'fields': [], 'methods': [], 'inherits': None, 'compositions': []}}
        self.selected_class = None
        
        # Główny widget i layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # Panel boczny do edycji klas
        self.side_panel = QWidget()
        self.side_panel.setFixedWidth(300)
        self.side_layout = QVBoxLayout(self.side_panel)
        
        # Panel do tworzenia/edycji klas
        self.create_class_group()
        self.create_fields_group()
        self.create_relations_group()
        
        # Drzewo klas
        self.class_tree = QTreeWidget()
        self.class_tree.setHeaderLabel("Struktura klas")
        self.main_layout.addWidget(self.side_panel)
        self.main_layout.addWidget(self.class_tree)
        
        # Inicjalizacja UI
        self.update_class_list()
        self.update_fields_list()
        
    def create_class_group(self):
        """Tworzy sekcję do zarządzania klasami"""
        group = QWidget()
        layout = QVBoxLayout(group)
        
        # Dodawanie nowej klasy
        self.class_name_input = QLineEdit()
        self.class_name_input.setPlaceholderText("Nazwa klasy")
        self.add_class_btn = QPushButton("Dodaj klasę")
        self.add_class_btn.clicked.connect(self.add_class)
        
        # Lista istniejących klas
        self.class_list = QListWidget()
        self.class_list.itemClicked.connect(self.select_class)
        self.delete_class_btn = QPushButton("Usuń klasę")
        self.delete_class_btn.clicked.connect(self.delete_class)
        
        layout.addWidget(QLabel("Dodaj nową klasę:"))
        layout.addWidget(self.class_name_input)
        layout.addWidget(self.add_class_btn)
        layout.addWidget(QLabel("Istniejące klasy:"))
        layout.addWidget(self.class_list)
        layout.addWidget(self.delete_class_btn)
        
        self.side_layout.addWidget(group)
    
    def create_fields_group(self):
        """Tworzy sekcję do zarządzania polami klasy"""
        group = QWidget()
        layout = QVBoxLayout(group)
        
        # Dodawanie nowego pola
        self.field_name_input = QLineEdit()
        self.field_name_input.setPlaceholderText("Nazwa pola")
        
        self.field_type_combo = QComboBox()
        self.field_type_combo.addItems(["str", "int", "float", "bool", "list", "dict"])
        
        self.add_field_btn = QPushButton("Dodaj pole")
        self.add_field_btn.clicked.connect(self.add_field)
        
        # Lista pól klasy
        self.fields_list = QListWidget()
        self.delete_field_btn = QPushButton("Usuń pole")
        self.delete_field_btn.clicked.connect(self.delete_field)
        
        layout.addWidget(QLabel("Dodaj nowe pole:"))
        layout.addWidget(self.field_name_input)
        layout.addWidget(QLabel("Typ pola:"))
        layout.addWidget(self.field_type_combo)
        layout.addWidget(self.add_field_btn)
        layout.addWidget(QLabel("Pola klasy:"))
        layout.addWidget(self.fields_list)
        layout.addWidget(self.delete_field_btn)
        
        self.side_layout.addWidget(group)
    
    def create_relations_group(self):
        """Tworzy sekcję do zarządzania relacjami między klasami"""
        group = QWidget()
        layout = QVBoxLayout(group)
        
        # Typ relacji
        self.relation_type_combo = QComboBox()
        self.relation_type_combo.addItems(["Dziedziczenie", "Kompozycja"])
        
        # Lista klas do wyboru dla relacji
        self.relation_target_combo = QComboBox()
        
        # Przyciski do zarządzania relacjami
        self.add_relation_btn = QPushButton("Dodaj relację")
        self.add_relation_btn.clicked.connect(self.add_relation)
        self.delete_relation_btn = QPushButton("Usuń relację")
        self.delete_relation_btn.clicked.connect(self.delete_relation)
        
        layout.addWidget(QLabel("Typ relacji:"))
        layout.addWidget(self.relation_type_combo)
        layout.addWidget(QLabel("Klasa docelowa:"))
        layout.addWidget(self.relation_target_combo)
        layout.addWidget(self.add_relation_btn)
        layout.addWidget(self.delete_relation_btn)
        
        self.side_layout.addWidget(group)
        self.side_layout.addStretch()
    
    def add_class(self):
        """Dodaje nową klasę do diagramu"""
        class_name = self.class_name_input.text().strip()
        if not class_name:
            QMessageBox.warning(self, "Błąd", "Nazwa klasy nie może być pusta!")
            return
        
        if class_name in self.classes:
            QMessageBox.warning(self, "Błąd", "Klasa o tej nazwie już istnieje!")
            return
        
        # Dodanie nowej klasy
        self.classes[class_name] = {
            'fields': [],
            'methods': [],
            'inherits': None,
            'compositions': []
        }
        
        # Aktualizacja UI
        self.class_name_input.clear()
        self.update_class_list()
        self.update_relation_targets()
        self.update_class_tree()
    
    def delete_class(self):
        """Usuwa wybraną klasę z diagramu"""
        if not self.selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy do usunięcia!")
            return
        
        # Usunięcie klasy i wszystkich relacji z nią związanych
        del self.classes[self.selected_class]
        
        # Usunięcie relacji związanych z tą klasą z innych klas
        for cls_name, cls_data in self.classes.items():
            if cls_data['inherits'] == self.selected_class:
                cls_data['inherits'] = None
            cls_data['compositions'] = [c for c in cls_data['compositions'] if c != self.selected_class]
        
        self.selected_class = None
        self.update_class_list()
        self.update_fields_list()
        self.update_relation_targets()
        self.update_class_tree()
    
    def select_class(self, item):
        """Wybierz klasę do edycji"""
        self.selected_class = item.text()
        self.update_fields_list()
        self.update_relation_targets()
    
    def add_field(self):
        """Dodaje nowe pole do wybranej klasy"""
        if not self.selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy!")
            return
        
        field_name = self.field_name_input.text().strip()
        if not field_name:
            QMessageBox.warning(self, "Błąd", "Nazwa pola nie może być pusta!")
            return
        
        field_type = self.field_type_combo.currentText()
        
        # Dodanie pola do klasy
        self.classes[self.selected_class]['fields'].append({
            'name': field_name,
            'type': field_type
        })
        
        # Aktualizacja UI
        self.field_name_input.clear()
        self.update_fields_list()
        self.update_class_tree()
    
    def delete_field(self):
        """Usuwa wybrane pole z klasy"""
        if not self.selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy!")
            return
        
        selected_items = self.fields_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie wybrano pola do usunięcia!")
            return
        
        field_name = selected_items[0].text().split(':')[0].strip()
        
        # Usunięcie pola
        self.classes[self.selected_class]['fields'] = [
            field for field in self.classes[self.selected_class]['fields'] 
            if field['name'] != field_name
        ]
        
        self.update_fields_list()
        self.update_class_tree()
    
    def add_relation(self):
        """Dodaje relację między klasami"""
        if not self.selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy źródłowej!")
            return
        
        target_class = self.relation_target_combo.currentText()
        if not target_class or target_class == self.selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano poprawnej klasy docelowej!")
            return
        
        relation_type = self.relation_type_combo.currentText()
        
        if relation_type == "Dziedziczenie":
            # Sprawdź, czy klasa już dziedziczy
            if self.classes[self.selected_class]['inherits']:
                QMessageBox.warning(self, "Błąd", "Klasa może dziedziczyć tylko po jednej klasie!")
                return
            
            # Sprawdź cykliczne dziedziczenie
            if self.check_inheritance_cycle(self.selected_class, target_class):
                QMessageBox.warning(self, "Błąd", "Wykryto cykliczne dziedziczenie!")
                return
            
            self.classes[self.selected_class]['inherits'] = target_class
            
        elif relation_type == "Kompozycja":
            if target_class in self.classes[self.selected_class]['compositions']:
                QMessageBox.warning(self, "Błąd", "Kompozycja już istnieje!")
                return
            
            self.classes[self.selected_class]['compositions'].append(target_class)
            
            # Dodaj pole z obiektem tej klasy
            field_name = target_class.lower() + "_obj"
            field_type = target_class
            
            self.classes[self.selected_class]['fields'].append({
                'name': field_name,
                'type': field_type
            })
        
        self.update_fields_list()
        self.update_class_tree()
    
    def check_inheritance_cycle(self, source, target):
        """Sprawdza cykliczne dziedziczenie"""
        current = target
        while current:
            if current == source:
                return True
            current = self.classes[current]['inherits']
        return False
    
    def delete_relation(self):
        """Usuwa relację z wybranej klasy"""
        if not self.selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy!")
            return
        
        relation_type = self.relation_type_combo.currentText()
        
        if relation_type == "Dziedziczenie":
            if not self.classes[self.selected_class]['inherits']:
                QMessageBox.warning(self, "Błąd", "Klasa nie dziedziczy po żadnej klasie!")
                return
            
            self.classes[self.selected_class]['inherits'] = None
            
        elif relation_type == "Kompozycja":
            target_class = self.relation_target_combo.currentText()
            if not target_class or target_class not in self.classes[self.selected_class]['compositions']:
                QMessageBox.warning(self, "Błąd", "Nie wybrano kompozycji do usunięcia!")
                return
            
            self.classes[self.selected_class]['compositions'].remove(target_class)
            
            # Usuń pole z obiektem tej klasy
            field_name = target_class.lower() + "_obj"
            self.classes[self.selected_class]['fields'] = [
                field for field in self.classes[self.selected_class]['fields'] 
                if field['name'] != field_name
            ]
        
        self.update_fields_list()
        self.update_class_tree()
    
    def update_class_list(self):
        """Aktualizuje listę klas w panelu bocznym"""
        self.class_list.clear()
        for class_name in self.classes:
            self.class_list.addItem(class_name)
    
    def update_fields_list(self):
        """Aktualizuje listę pól wybranej klasy"""
        self.fields_list.clear()
        
        if not self.selected_class or self.selected_class not in self.classes:
            return
        
        # Pola własne klasy
        for field in self.classes[self.selected_class]['fields']:
            self.fields_list.addItem(f"{field['name']}: {field['type']}")
        
        # Pola dziedziczone
        if self.classes[self.selected_class]['inherits']:
            parent_class = self.classes[self.selected_class]['inherits']
            while parent_class:
                for field in self.classes[parent_class]['fields']:
                    self.fields_list.addItem(f"{field['name']}: {field['type']} (dziedziczone z {parent_class})")
                parent_class = self.classes[parent_class]['inherits']
    
    def update_relation_targets(self):
        """Aktualizuje listę dostępnych klas dla relacji"""
        self.relation_target_combo.clear()
        
        if not self.selected_class:
            return
        
        # Dodaj wszystkie klasy oprócz aktualnie wybranej
        for class_name in self.classes:
            if class_name != self.selected_class:
                self.relation_target_combo.addItem(class_name)
    
    def update_class_tree(self):
        """Aktualizuje drzewo klas"""
        self.class_tree.clear()
        
        # Dodaj klasy bez rodziców na początek
        for class_name, class_data in self.classes.items():
            if not class_data['inherits']:
                self.add_class_to_tree(class_name)
        
        # Dodaj pozostałe klasy (w przypadku cykli)
        for class_name in self.classes:
            if not self.find_class_in_tree(class_name):
                self.add_class_to_tree(class_name)
    
    def add_class_to_tree(self, class_name):
        """Dodaje klasę do drzewa z uwzględnieniem dziedziczenia"""
        class_item = QTreeWidgetItem([class_name])
        self.class_tree.addTopLevelItem(class_item)
        
        # Dodaj pola klasy
        for field in self.classes[class_name]['fields']:
            field_item = QTreeWidgetItem([f"{field['name']}: {field['type']}"])
            class_item.addChild(field_item)
        
        # Dodaj kompozycje
        if self.classes[class_name]['compositions']:
            comp_item = QTreeWidgetItem(["Kompozycje:"])
            class_item.addChild(comp_item)
            for comp in self.classes[class_name]['compositions']:
                comp_child = QTreeWidgetItem([comp])
                comp_item.addChild(comp_child)
        
        # Dodaj dzieci (klasy dziedziczące)
        for child_name, child_data in self.classes.items():
            if child_data['inherits'] == class_name:
                child_item = self.add_class_to_tree(child_name)
                class_item.addChild(child_item)
        
        return class_item
    
    def find_class_in_tree(self, class_name):
        """Sprawdza, czy klasa już istnieje w drzewie"""
        items = self.class_tree.findItems(class_name, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        return bool(items)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ClassDiagramEditor()
    window.show()
    sys.exit(app.exec())