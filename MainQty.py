import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFormLayout, QScrollArea, QFileDialog # Added QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont # For styling tree items
from typing import Dict, List, Optional, Any

# Define type aliases for clarity
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]

class ClassDiagramEditor(QMainWindow):
    # Signal emitted when the list of classes changes
    classes_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Edytor Diagramów Klas i Obiektów")
        self.setGeometry(100, 100, 1100, 750) # Slightly larger window

        # --- Data aplikacji ---
        self.classes: ClassesDict = {}
        self.selected_class_editor: Optional[str] = None # Selection in editor mode

        # --- UI Elements ---

        # --- Konfiguracja głównego UI ---
        self.mode_switch_button = None
        self._switch_mode = None
        self._setup_main_ui()

        # --- Inicjalizacja stanu UI ---
        self._update_all_class_editor_views()



    def _setup_main_ui(self):
        """Konfiguruje główny interfejs z przełączaniem trybów."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Górny pasek: Przełączanie trybów i Generowanie Kodu ---

        self.generate_code_button = QPushButton("Generuj kod Pythona i zapisz")
        self.generate_code_button.clicked.connect(self._save_python_code) # Connect to save function
        top_bar_layout = QHBoxLayout()  # Define top_bar_layout as QHBoxLayout
        top_bar_layout.addWidget(self.generate_code_button)
        top_bar_layout.addStretch() # Push buttons to the left

        main_layout.addLayout(top_bar_layout) # Add the button bar layout

        # --- QStackedWidget do przełączania widoków ---
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # --- Strona 1: Edytor Klas ---
        self.class_editor_widget = self._create_class_editor_widget()
        self.stacked_widget.addWidget(self.class_editor_widget)


    def _get_type_hint_str(self, type_name: str, is_composition: bool) -> str:
        """Generates a Python type hint string."""
        if type_name in ["str", "int", "float", "bool"]:
            return type_name
        elif type_name == "list":
            return "List" # Needs 'from typing import List'
        elif type_name == "dict":
            return "Dict" # Needs 'from typing import Dict'
        elif type_name in self.classes:
            # Use string literal for forward reference for classes
            # Mark compositions as Optional, assuming they might not be set initially
            hint = f"'{type_name}'"
            if is_composition:
                hint = f"Optional[{hint}]" # Needs 'from typing import Optional'
            return hint
        else:
            return "Any" # Needs 'from typing import Any'

    def _generate_python_code(self) -> str:
        """Generates Python code string from class and object data."""
        code_lines = []
        if not self.classes:
            return ""


        # --- Imports ---
        imports = {"Any", "Optional", "List", "Dict"}
        code_lines.append(f"from typing import {', '.join(sorted(list(imports)))}")
        code_lines.append("\n")

        # --- Class Definitions ---
        code_lines.append("# --- Class Definitions ---")

        sorted_classes = self._sort_classes_by_inheritance()

        for class_name in sorted_classes:
            if class_name not in self.classes:
                continue

            class_data = self.classes[class_name]
            parent_name = class_data.get('inherits')
            compositions = class_data.get('compositions', [])
            own_fields = class_data.get('fields', [])

            # Pobierz pola klasy bazowej jeśli istnieje
            parent_fields = []
            parent_compositions = []
            if parent_name and parent_name in self.classes:
                parent_fields = self.classes[parent_name].get('fields', [])
                parent_compositions = self.classes[parent_name].get('compositions', [])

            # Dziedziczenie
            parent_str = f"({parent_name})" if parent_name else "(object)"
            code_lines.append(f"\nclass {class_name}{parent_str}:")

            # Funkcja pomocnicza do podziału pól na wymagane i opcjonalne
            def split_fields(fields, compositions_list):
                required = []
                optional = []
                for f in fields:
                    is_comp = self._is_composition_field(f['name'], f['type'], compositions_list)
                    if is_comp:
                        optional.append(f)
                    else:
                        required.append(f)
                return required, optional

            # Podziel pola klasy bazowej i własne
            parent_required, parent_optional = split_fields(parent_fields, parent_compositions)
            own_required, own_optional = split_fields(own_fields, compositions)

            # Buduj listę parametrów __init__
            init_params = ['self']

            # Najpierw pola wymagane klasy bazowej
            for f in sorted(parent_required, key=lambda x: x['name']):
                type_hint = self._get_type_hint_str(f['type'], False)
                init_params.append(f"{f['name']}: {type_hint}")

            # Pola wymagane klasy potomnej
            for f in sorted(own_required, key=lambda x: x['name']):
                type_hint = self._get_type_hint_str(f['type'], False)
                init_params.append(f"{f['name']}: {type_hint}")

            # Pola opcjonalne klasy bazowej
            for f in sorted(parent_optional, key=lambda x: x['name']):
                type_hint = self._get_type_hint_str(f['type'], True)
                init_params.append(f"{f['name']}: {type_hint} = None")

            # Pola opcjonalne klasy potomnej
            for f in sorted(own_optional, key=lambda x: x['name']):
                type_hint = self._get_type_hint_str(f['type'], True)
                init_params.append(f"{f['name']}: {type_hint} = None")

            # Jeśli brak parametrów i brak rodzica - daj pass
            if len(init_params) == 1 and not parent_name:
                code_lines.append("    pass")
                continue

            code_lines.append(f"    def __init__({', '.join(init_params)}):")

            # Wywołanie super().__init__ z argumentami klasy bazowej
            if parent_name:
                super_args = []
                for f in sorted(parent_required, key=lambda x: x['name']):
                    super_args.append(f"{f['name']}")
                for f in sorted(parent_optional, key=lambda x: x['name']):
                    super_args.append(f"{f['name']}={f['name']}")
                code_lines.append(f"        super().__init__({', '.join(super_args)})")

            # Przypisania własnych pól klasy (pomijamy pola bazowe)
            parent_field_names = {f['name'] for f in parent_fields} if parent_name else set()
            for f in sorted(own_required + own_optional, key=lambda x: x['name']):
                if f['name'] not in parent_field_names:
                    code_lines.append(f"        self.{f['name']} = {f['name']}")

            # Jeśli brak przypisań i brak super(), daj pass
            code_lines.append("    pass # No objects defined")
        return "\n".join(code_lines)
    def _sort_classes_by_inheritance(self) -> List[str]:
        """Sorts classes so that parent classes come before child classes."""
        class_order = []
        remaining_classes = set(self.classes.keys())
        
        while remaining_classes:
            # Find classes that have no parents or whose parents are already processed
            ready_classes = [
                cls for cls in remaining_classes
                if not self.classes[cls].get('inherits') or 
                self.classes[cls]['inherits'] not in remaining_classes
            ]
            
            if not ready_classes:
                # Circular dependency - pick one arbitrarily
                cls = next(iter(remaining_classes))
                ready_classes = [cls]
                print(f"Warning: Circular inheritance detected involving {cls}")
                
            class_order.extend(sorted(ready_classes))
            remaining_classes -= set(ready_classes)
        
        return class_order

    def _save_python_code(self):
        """Generates Python code and prompts the user to save it to a file."""
        if not self.classes:
            QMessageBox.information(self, "Brak Klas", "Nie zdefiniowano żadnych klas do wygenerowania kodu.")
            return

        generated_code = self._generate_python_code()        

        # --- Prompt user for save location ---
        default_filename = "wygenerowany_kod.py"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz kod Pythona",
            default_filename,
            "Python Files (*.py);;All Files (*)"
        )

        if file_path: # If the user didn't cancel
            if generated_code == "":
                QMessageBox.information(self, "Brak klas", "Nie ma klas do wygenerowania.")
                return
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(generated_code)
                QMessageBox.information(self, "Sukces", f"Kod Pythona został zapisany do:\n{file_path}")
            except IOError as e:
                QMessageBox.critical(self, "Błąd Zapisu", f"Nie można zapisać pliku:\n{e}")
            except Exception as e:
                 QMessageBox.critical(self, "Błąd Generowania/Zapisu", f"Wystąpił nieoczekiwany błąd:\n{e}")

    def _create_class_editor_widget(self) -> QWidget:
        """Tworzy widget dla trybu edycji klas."""
        editor_widget = QWidget()
        editor_layout = QHBoxLayout(editor_widget)

        # --- Panel boczny (kontener) ---
        side_panel = QWidget()
        side_panel.setFixedWidth(350) # Slightly wider
        self.side_layout = QVBoxLayout(side_panel) # Store side_layout if needed elsewhere, maybe not
        self.side_layout.setContentsMargins(5, 5, 5, 5)
        self.side_layout.setSpacing(10)

        # --- Tworzenie i dodawanie paneli do layoutu bocznego ---
        # Store references to the panels on self
        self.class_management_panel = self._create_class_management_panel()
        self.fields_management_panel = self._create_fields_management_panel()
        self.relations_management_panel = self._create_relations_management_panel()

        self.side_layout.addWidget(self.class_management_panel)
        self.side_layout.addWidget(self.fields_management_panel)
        self.side_layout.addWidget(self.relations_management_panel)
        self.side_layout.addStretch()

        # --- Drzewo klas ---
        self.class_tree = QTreeWidget()
        self.class_tree.setHeaderLabel("Struktura klas")

        # --- Dodawanie panelu bocznego i drzewa do layoutu edytora ---
        editor_layout.addWidget(side_panel)
        editor_layout.addWidget(self.class_tree)

        return editor_widget

    # --- Metody zarządzania UI Edytora Klas (lekko zmodyfikowane nazwy widgetów) ---

    def _create_class_management_panel(self) -> QWidget:
        """Tworzy panel do zarządzania klasami w edytorze."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("<b>Zarządzanie klasami:</b>"))
        self.editor_class_name_input = QLineEdit()
        self.editor_class_name_input.setPlaceholderText("Nazwa nowej klasy")
        self.editor_add_class_btn = QPushButton("Dodaj klasę")

        self.editor_class_list = QListWidget()
        self.editor_delete_class_btn = QPushButton("Usuń zaznaczoną klasę")

        layout.addWidget(self.editor_class_name_input)
        layout.addWidget(self.editor_add_class_btn)
        layout.addWidget(QLabel("Istniejące klasy:"))
        layout.addWidget(self.editor_class_list)
        layout.addWidget(self.editor_delete_class_btn)

        self.editor_add_class_btn.clicked.connect(self.add_class)
        self.editor_class_list.itemClicked.connect(self.select_class_editor) # Use specific handler
        self.editor_delete_class_btn.clicked.connect(self.delete_class)

        return panel

    def _create_fields_management_panel(self) -> QWidget:
        """Tworzy panel do zarządzania polami w edytorze."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("<b>Zarządzanie polami (dla wybranej klasy):</b>"))
        self.editor_field_name_input = QLineEdit()
        self.editor_field_name_input.setPlaceholderText("Nazwa nowego pola")

        self.editor_field_type_combo = QComboBox()
        self.editor_field_type_combo.addItems(["str", "int", "float", "bool", "list", "dict"])

        self.editor_add_field_btn = QPushButton("Dodaj pole")

        self.editor_fields_list = QListWidget()
        self.editor_delete_field_btn = QPushButton("Usuń zaznaczone pole")

        layout.addWidget(self.editor_field_name_input)
        layout.addWidget(QLabel("Typ pola:"))
        layout.addWidget(self.editor_field_type_combo)
        layout.addWidget(self.editor_add_field_btn)
        layout.addWidget(QLabel("Pola w klasie (własne i dziedziczone):"))
        layout.addWidget(self.editor_fields_list)
        layout.addWidget(self.editor_delete_field_btn)

        self.editor_add_field_btn.clicked.connect(self.add_field)
        self.editor_delete_field_btn.clicked.connect(self.delete_field)
        
        # Disable initially until a class is selected
        panel.setEnabled(False) 

        return panel

    def _create_relations_management_panel(self) -> QWidget:
        """Tworzy panel do zarządzania relacjami w edytorze."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("<b>Zarządzanie relacjami (dla wybranej klasy):</b>"))

        self.editor_relation_type_combo = QComboBox()
        self.editor_relation_type_combo.addItems(["Dziedziczenie", "Kompozycja"])

        self.editor_relation_target_combo = QComboBox()

        self.editor_add_relation_btn = QPushButton("Dodaj relację")
        self.editor_delete_relation_btn = QPushButton("Usuń relację") # Consider dynamic label

        layout.addWidget(QLabel("Typ relacji:"))
        layout.addWidget(self.editor_relation_type_combo)
        layout.addWidget(QLabel("Klasa docelowa:"))
        layout.addWidget(self.editor_relation_target_combo)
        layout.addWidget(self.editor_add_relation_btn)
        layout.addWidget(self.editor_delete_relation_btn)

        self.editor_add_relation_btn.clicked.connect(self.add_relation)
        self.editor_delete_relation_btn.clicked.connect(self.delete_relation)
        
        # Disable initially until a class is selected
        panel.setEnabled(False) 

        return panel
        
    # --- Metody logiki biznesowej (klasy) ---

    def add_class(self):
        """Dodaje nową klasę do diagramu i wybiera ją do edycji"""
        class_name = self.editor_class_name_input.text().strip()
        if not class_name or not class_name[0].isupper(): # Enforce capital letter start
            QMessageBox.warning(self, "Błąd", "Nazwa klasy musi zaczynać się wielką literą i nie może być pusta!")
            return

        if class_name in self.classes:
            QMessageBox.warning(self, "Błąd", "Klasa o tej nazwie już istnieje!")
            return

        # Add class data
        self.classes[class_name] = {
            'fields': [], 'methods': [], 'inherits': None, 'compositions': []
        }
        self.editor_class_name_input.clear()

        # --- Update UI and Select New Class ---
        self._update_editor_class_list() # Update the list widget first

        # Find the newly added item in the list
        items = self.editor_class_list.findItems(class_name, Qt.MatchFlag.MatchExactly)
        if items:
            list_item = items[0]
            self.editor_class_list.setCurrentItem(list_item) # Select the new item in the list UI
            self.select_class_editor(list_item) # Manually call the selection logic
        else:
            # Should not happen if update worked, but handle defensively
             self.selected_class_editor = None
             self._enable_editor_panels(False)


        # Update other relevant parts of the UI
        self._update_editor_field_type_combo()
        self.update_class_tree()
    def delete_class(self):
        """Usuwa wybraną klasę z diagramu (i powiązane obiekty)"""
        current_selection = self.editor_class_list.currentItem()
        if not current_selection:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy do usunięcia!")
            return
        class_to_delete = current_selection.text()

        warning_msg = ""
        reply = QMessageBox.question(self, "Potwierdzenie usunięcia klasy",
                                     f"Czy na pewno chcesz usunąć klasę '{class_to_delete}' "
                                     f"oraz wszystkie powiązane z nią relacje?{warning_msg}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        # --- Delete class definition ---
        del self.classes[class_to_delete]

        # --- Clean up relations in other classes ---
        for cls_name, cls_data in self.classes.items():
            if cls_data['inherits'] == class_to_delete:
                cls_data['inherits'] = None
            # Remove compositions pointing to the deleted class
            if class_to_delete in cls_data['compositions']:
                cls_data['compositions'].remove(class_to_delete)
            # Remove fields that were compositions of the deleted class
            cls_data['fields'] = [
                f for f in cls_data['fields']
                if not (f['type'] == class_to_delete and self._is_composition_field(f['name'], f['type'], cls_data.get('compositions',[])))
            ]
            # Also remove fields whose *type* was the deleted class (even if not composition)
            cls_data['fields'] = [f for f in cls_data['fields'] if f['type'] != class_to_delete]
            
        # --- Update UI ---
        if self.selected_class_editor == class_to_delete:
            self.selected_class_editor = None
            self.editor_class_list.setCurrentItem(None)
            # Disable panels if no class is selected
            self._enable_editor_panels(False)

        self._update_all_class_editor_views()


    def select_class_editor(self, item: QListWidgetItem):
        """Wybierz klasę do edycji w trybie edytora."""
        self.selected_class_editor = item.text()
        self._update_editor_fields_list()
        self._update_editor_relation_targets()
        # Enable editing panels
        self._enable_editor_panels(True)


    def _enable_editor_panels(self, enabled: bool):
        """Włącza lub wyłącza panele edycji pól i relacji."""
        # Assuming the panels are direct children of the side layout
        # Need to access them directly or store references
        # Let's find them by searching the side_panel's children (less robust)
        # A better way is to store references like self.fields_panel = ...
        
        # Simplified: Find the panels by their QWidget container if they were stored
        # For now, let's assume we have references (need to store them in _create_...):
        if hasattr(self, 'fields_management_panel'): # Check if attribute exists
             self.fields_management_panel.setEnabled(enabled)
        if hasattr(self, 'relations_management_panel'):
             self.relations_management_panel.setEnabled(enabled)
             
        # If not storing references, you'd need a more complex findChild approach.


    def add_field(self):
        """Dodaje nowe pole do wybranej klasy w edytorze."""
        if not self.selected_class_editor: return # Should be prevented by panel state

        field_name = self.editor_field_name_input.text().strip()
        # Basic validation: starts with lowercase, no spaces
        if not field_name or not field_name[0].islower() or ' ' in field_name:
            QMessageBox.warning(self, "Błąd", "Nazwa pola musi zaczynać się małą literą i nie może zawierać spacji.")
            return

        all_fields_data = self._get_all_fields_recursive(self.selected_class_editor)
        existing_fields = set(f['field']['name'] for f in all_fields_data)
        if field_name in existing_fields:
             QMessageBox.warning(self, "Błąd", f"Pole o nazwie '{field_name}' już istnieje w tej klasie lub klasie nadrzędnej.")
             return


        field_type = self.editor_field_type_combo.currentText()  # Retrieve the selected field type
        self.classes[self.selected_class_editor]['fields'].append({
            'name': field_name, 'type': field_type
        })

        self.editor_field_name_input.clear()
        self._update_editor_fields_list()
        self.update_class_tree() # Update tree view in editor

    def delete_field(self):
        """Usuwa wybrane pole z klasy w edytorze."""
        if not self.selected_class_editor: return

        selected_items = self.editor_fields_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie wybrano pola do usunięcia!")
            return

        item_text = selected_items[0].text()
        field_name = item_text.split(':')[0].strip() # Get the name part

        # Check if the field is inherited
        if "(dziedziczone z" in item_text:
             QMessageBox.warning(self, "Błąd", "Nie można usunąć pola dziedziczonego. Usuń je w klasie bazowej.")
             return

        # Check if the field represents a composition managed elsewhere
        field_data = next((f for f in self.classes[self.selected_class_editor]['fields'] if f['name'] == field_name), None)
        if field_data and self._is_composition_field(field_name, field_data['type'], self.classes[self.selected_class_editor].get('compositions',[])):
             QMessageBox.warning(self, "Błąd", f"To pole reprezentuje kompozycję '{field_data['type']}'. Usuń relację kompozycji, aby usunąć to pole.")
             return

        # Proceed with deletion
        initial_len = len(self.classes[self.selected_class_editor]['fields'])
        self.classes[self.selected_class_editor]['fields'] = [
            field for field in self.classes[self.selected_class_editor]['fields']
            if field['name'] != field_name
        ]

        if len(self.classes[self.selected_class_editor]['fields']) < initial_len:
             self._update_editor_fields_list()
             self.update_class_tree()
        else:
             QMessageBox.information(self,"Info", f"Nie znaleziono własnego pola o nazwie '{field_name}' do usunięcia.")


    def add_relation(self):
        """Dodaje relację między klasami w edytorze."""
        if not self.selected_class_editor: return

        target_class = self.editor_relation_target_combo.currentText()
        if not target_class:
             QMessageBox.warning(self, "Błąd", "Nie wybrano klasy docelowej relacji.")
             return

        relation_type = self.editor_relation_type_combo.currentText()
        source_class = self.selected_class_editor
        source_data = self.classes[source_class]

        if relation_type == "Dziedziczenie":
            if source_data['inherits'] and source_data['inherits'] != target_class:
                reply = QMessageBox.question(self, "Zmiana dziedziczenia",
                                     f"Klasa '{source_class}' już dziedziczy po '{source_data['inherits']}'. Zmienić na '{target_class}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No: return
            elif source_data['inherits'] == target_class:
                 QMessageBox.information(self,"Info", f"Klasa '{source_class}' już dziedziczy po '{target_class}'.")
                 return

            if self.check_inheritance_cycle(source_class, target_class):
                QMessageBox.warning(self, "Błąd cyklu", f"Ustawienie dziedziczenia po '{target_class}' utworzyłoby cykl!")
                return

            source_data['inherits'] = target_class
            QMessageBox.information(self, "Sukces", f"Ustawiono dziedziczenie: {source_class} -> {target_class}")

        elif relation_type == "Kompozycja":
            if target_class in source_data['compositions']:
                QMessageBox.warning(self, "Błąd", f"Kompozycja z klasą '{target_class}' już istnieje!")
                return

            source_data['compositions'].append(target_class)

            # --- Auto-add field for composition ---
            field_name = self._generate_composition_field_name(source_class, target_class)
            field_type = target_class
            source_data['fields'].append({'name': field_name, 'type': field_type})

            QMessageBox.information(self, "Sukces", f"Dodano kompozycję: {source_class} --<> {target_class} (pole '{field_name}')")

        self._update_all_class_editor_views() # Update all related views in editor


    def delete_relation(self):
        """Usuwa relację z wybranej klasy w edytorze."""
        if not self.selected_class_editor: return

        relation_type = self.editor_relation_type_combo.currentText()
        target_class = self.editor_relation_target_combo.currentText() # May be empty if list is empty
        source_class = self.selected_class_editor
        source_data = self.classes[source_class]

        if relation_type == "Dziedziczenie":
            current_inheritance = source_data['inherits']
            if not current_inheritance:
                QMessageBox.warning(self, "Błąd", f"Klasa '{source_class}' nie dziedziczy.")
                return

            reply = QMessageBox.question(self, "Potwierdzenie",
                                         f"Usunąć dziedziczenie klasy '{source_class}' po '{current_inheritance}'?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                source_data['inherits'] = None
                QMessageBox.information(self, "Sukces", f"Usunięto dziedziczenie po '{current_inheritance}'.")

        elif relation_type == "Kompozycja":
            if not target_class:
                 QMessageBox.warning(self, "Błąd", "Nie wybrano klasy docelowej dla kompozycji.")
                 return
            if target_class not in source_data['compositions']:
                QMessageBox.warning(self, "Błąd", f"Klasa '{source_class}' nie ma kompozycji z '{target_class}'.")
                return

            reply = QMessageBox.question(self, "Potwierdzenie",
                                         f"Usunąć kompozycję klasy '{source_class}' z '{target_class}' (usunie też powiązane pole)?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                source_data['compositions'].remove(target_class)

                # --- Auto-remove composition field ---
                removed_field_name = None
                fields_to_keep = []
                for field in source_data['fields']:
                    if self._is_composition_field(field['name'], field['type'], [target_class]): # Check against the removed target
                        removed_field_name = field['name']
                    else:
                        fields_to_keep.append(field)
                source_data['fields'] = fields_to_keep

                if removed_field_name:
                    QMessageBox.information(self, "Sukces", f"Usunięto kompozycję z '{target_class}' (usunięto pole '{removed_field_name}').")
                else:
                    QMessageBox.information(self, "Sukces", f"Usunięto kompozycję z '{target_class}'. Nie znaleziono pola do usunięcia.")


        self._update_all_class_editor_views() # Update all related views

    # --- Metody pomocnicze logiki (cykle, pola) ---

    def check_inheritance_cycle(self, source: str, target: str) -> bool:
        """Sprawdza cykliczne dziedziczenie"""
        current = target
        visited = {current}
        while current:
            parent = self.classes.get(current, {}).get('inherits')
            if not parent: return False # Reached top
            if parent == source: return True # Direct cycle
            if parent in visited: return True # Indirect cycle
            visited.add(parent)
            current = parent
        return False

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        """Rekurencyjnie pobiera WSZYSTKIE unikalne pola (własne i dziedziczone)."""
        if class_name not in self.classes: return []
        if visited is None: visited = set() # Prevent infinite loops in erroneous cycles
        if class_name in visited: return []
        visited.add(class_name)

        fields_map: Dict[str, Dict[str, Any]] = {}

        # Get fields from parent first
        parent_class = self.classes[class_name].get('inherits')
        if parent_class:
            parent_fields_data = self._get_all_fields_recursive(parent_class, visited.copy())
            for field_info in parent_fields_data:
                fields_map[field_info['field']['name']] = field_info

        # Get own fields (overwrite parent fields with the same name)
        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source': class_name}

        return list(fields_map.values())
        
    def _is_composition_field(self, field_name: str, field_type: str, composition_targets: List[str]) -> bool:
        """Checks if a field likely represents one of the given composition targets."""
        if field_type not in composition_targets:
            return False
        # Check naming convention: starts with lowercase class name, ends with _obj or _obj<number>
        base_name = field_type.lower()
        if field_name.startswith(base_name):
             suffix = field_name[len(base_name):]
             return suffix == "_obj" or (suffix.startswith("_obj") and suffix[4:].isdigit())
        return False

    def _generate_composition_field_name(self, source_class: str, target_class: str) -> str:
        """Generates a unique field name for a composition."""
        base_field_name = target_class.lower()
        field_name = base_field_name + "_obj"
        counter = 1
        # Need *all* fields (own + inherited) for uniqueness check
        existing_field_names = set(f['field']['name'] for f in self._get_all_fields_recursive(source_class))
        while field_name in existing_field_names:
             counter += 1
             field_name = f"{base_field_name}_obj{counter}" # Change suffix for uniqueness
        return field_name


    # --- Metody aktualizacji UI Edytora Klas ---

    def _update_all_class_editor_views(self):
        """Aktualizuje wszystkie widoki w edytorze klas."""
        self._update_editor_class_list()
        self._update_editor_fields_list() # Depends on selected_class_editor
        self._update_editor_relation_targets() # Depends on selected_class_editor
        self._update_editor_field_type_combo()
        self.update_class_tree()

    def _update_editor_class_list(self):
        """Aktualizuje listę klas w panelu bocznym edytora."""
        self.editor_class_list.clear()
        sorted_class_names = sorted(self.classes.keys())
        self.editor_class_list.addItems(sorted_class_names)
        # Restore selection
        if self.selected_class_editor in self.classes:
             items = self.editor_class_list.findItems(self.selected_class_editor, Qt.MatchFlag.MatchExactly)
             if items: self.editor_class_list.setCurrentItem(items[0])
        else:
             # If selected class was deleted, clear selection and disable panels
             self.selected_class_editor = None
             self._enable_editor_panels(False)


    def _update_editor_fields_list(self):
        """Aktualizuje listę pól wybranej klasy w edytorze."""
        self.editor_fields_list.clear()
        if not self.selected_class_editor: return

        all_fields_data = self._get_all_fields_recursive(self.selected_class_editor)

        for field_info in sorted(all_fields_data, key=lambda x: x['field']['name']): # Sort fields alphabetically
            field = field_info['field']
            source = field_info['source']
            display_text = f"{field['name']}: {field['type']}"
            item = QListWidgetItem(display_text)
            
            # Mark inherited fields
            if source != self.selected_class_editor:
                # Make inherited fields visually distinct and non-selectable for deletion
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                item.setForeground(Qt.GlobalColor.gray)
                item.setText(display_text + f" (z {source})")
                # Prevent selecting inherited items for deletion
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable) 
            
            self.editor_fields_list.addItem(item)

    def _update_editor_relation_targets(self):
        """Aktualizuje listę dostępnych klas dla relacji w edytorze."""
        self.editor_relation_target_combo.clear()
        if not self.selected_class_editor: return

        available_targets = sorted([
            name for name in self.classes if name != self.selected_class_editor
        ])
        self.editor_relation_target_combo.addItems(available_targets)

    def _update_editor_field_type_combo(self):
        """Aktualizuje listę typów pól w edytorze."""
        current_selection = self.editor_field_type_combo.currentText()
        self.editor_field_type_combo.clear()
        basic_types = ["str", "int", "float", "bool", "list", "dict"]
        self.editor_field_type_combo.addItems(basic_types)
        class_names = sorted(self.classes.keys())
        if class_names:
             self.editor_field_type_combo.insertSeparator(len(basic_types))
             self.editor_field_type_combo.addItems(class_names)

        index = self.editor_field_type_combo.findText(current_selection)
        if index != -1: self.editor_field_type_combo.setCurrentIndex(index)
        elif self.editor_field_type_combo.count() > 0: self.editor_field_type_combo.setCurrentIndex(0)

    def update_class_tree(self):
        """Aktualizuje drzewo klas w edytorze."""
        self.class_tree.clear()
        added_items: Dict[str, QTreeWidgetItem] = {}

        def add_node(class_name: str) -> Optional[QTreeWidgetItem]:
            if class_name not in self.classes: return None
            if class_name in added_items: return added_items[class_name]

            class_data = self.classes[class_name]
            class_item = QTreeWidgetItem([class_name])
            added_items[class_name] = class_item

            # --- Pola (tylko własne) ---
            own_fields = class_data.get('fields', [])
            compositions = class_data.get('compositions', [])
            if own_fields:
                fields_node = QTreeWidgetItem(["Pola:"])
                font = fields_node.font(0)
                font.setBold(True)
                fields_node.setFont(0, font)
                class_item.addChild(fields_node)
                
                for field in sorted(own_fields, key=lambda x: x['name']):
                     # Don't list fields representing compositions here, list them below
                     if not self._is_composition_field(field['name'], field['type'], compositions):
                         field_item = QTreeWidgetItem([f"  {field['name']}: {field['type']}"])
                         fields_node.addChild(field_item)
                if fields_node.childCount() == 0: class_item.removeChild(fields_node)


            # --- Kompozycje ---
            if compositions:
                comp_node = QTreeWidgetItem(["Kompozycje:"])
                font = comp_node.font(0)
                font.setBold(True)
                comp_node.setFont(0, font)
                class_item.addChild(comp_node)
                for comp_target in sorted(compositions):
                    comp_child = QTreeWidgetItem([f"  <>-- {comp_target}"])
                    comp_node.addChild(comp_child)

            # --- Dzieci (rekurencja) ---
            # This logic builds bottom-up, let's try top-down instead below

            return class_item

        # Top-down build: Start with root classes (no inheritance)
        root_classes = sorted([name for name, data in self.classes.items() if not data.get('inherits')])
        processed_classes = set()

        items_to_add = []
        for root_name in root_classes:
             item = add_node(root_name)
             if item: items_to_add.append(item)
             processed_classes.add(root_name)

        # Build the hierarchy recursively
        def build_hierarchy(parent_item: QTreeWidgetItem, parent_name: str):
            children = sorted([name for name, data in self.classes.items() if data.get('inherits') == parent_name])
            for child_name in children:
                 if child_name not in processed_classes:
                     child_item = add_node(child_name)
                     if child_item:
                          parent_item.addChild(child_item)
                          processed_classes.add(child_name)
                          build_hierarchy(child_item, child_name) # Recurse

        for item in items_to_add:
             build_hierarchy(item, item.text(0))
        
        # Add any remaining classes (e.g., if there were cycles or orphaned classes)
        for class_name in sorted(self.classes.keys()):
             if class_name not in processed_classes:
                 item = add_node(class_name)
                 if item: items_to_add.append(item)

        self.class_tree.addTopLevelItems(items_to_add)
        self.class_tree.expandAll()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ClassDiagramEditor()
    window.show()
    sys.exit(app.exec())