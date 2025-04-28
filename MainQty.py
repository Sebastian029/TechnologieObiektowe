import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFormLayout, QScrollArea, QFileDialog # Added QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal # Added pyqtSignal
from PyQt6.QtGui import QFont # For styling tree items
from typing import Dict, List, Optional, Any, Tuple # Import types for hinting

# Define type aliases for clarity
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any] # {'class': str, 'attributes': Dict[str, Any]}
ObjectsDict = Dict[str, ObjectData]

class ClassDiagramEditor(QMainWindow):
    # Signal emitted when the list of classes changes
    classes_changed = pyqtSignal() 
    # Signal emitted when the list of objects changes
    objects_changed = pyqtSignal() 

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Edytor Diagramów Klas i Obiektów")
        self.setGeometry(100, 100, 1100, 750) # Slightly larger window

        # --- Data aplikacji ---
        self.classes: ClassesDict = {}
        self.objects: ObjectsDict = {} # Store created objects
        self.selected_class_editor: Optional[str] = None # Selection in editor mode

        # --- UI Elements ---
        # References to dynamically created input widgets for object creation
        self._object_input_widgets: List[Tuple[str, QWidget]] = [] 

        # --- Konfiguracja głównego UI ---
        self._setup_main_ui()

        # --- Inicjalizacja stanu UI ---
        self._update_all_class_editor_views()
        self._update_object_creator_view() # Initial setup for object creator

        # Connect signals for inter-view updates
        self.classes_changed.connect(self._update_object_class_combo)
        self.objects_changed.connect(self._update_object_tree)
        self.objects_changed.connect(self._update_composition_combos) # Update combos when objects change


    def _setup_main_ui(self):
        """Konfiguruje główny interfejs z przełączaniem trybów."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Górny pasek: Przełączanie trybów i Generowanie Kodu ---
        top_bar_layout = QHBoxLayout() # Layout for buttons at the top
        self.mode_switch_button = QPushButton("Przejdź do tworzenia obiektów")
        self.mode_switch_button.clicked.connect(self._switch_mode)
        top_bar_layout.addWidget(self.mode_switch_button)

        self.generate_code_button = QPushButton("Generuj kod Pythona i zapisz")
        self.generate_code_button.clicked.connect(self._save_python_code) # Connect to save function
        top_bar_layout.addWidget(self.generate_code_button)
        top_bar_layout.addStretch() # Push buttons to the left

        main_layout.addLayout(top_bar_layout) # Add the button bar layout

        # --- QStackedWidget do przełączania widoków ---
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # --- Strona 1: Edytor Klas ---
        self.class_editor_widget = self._create_class_editor_widget()
        self.stacked_widget.addWidget(self.class_editor_widget)

        # --- Strona 2: Kreator Obiektów ---
        self.object_creator_widget = self._create_object_creator_widget()
        self.stacked_widget.addWidget(self.object_creator_widget)


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
            if not own_required and not own_optional and not parent_name:
                code_lines.append("        pass")

            code_lines.append("")  # Pusta linia po klasie

        # --- Object Instantiation ---
        code_lines.append("\n# --- Object Instantiation ---")
        code_lines.append("# Note: Object creation order might matter based on compositions.")
        code_lines.append("if __name__ == '__main__':")

        if not self.objects:
            code_lines.append("    pass # No objects defined")
        else:
            object_creation_lines = []
            for obj_name in sorted(self.objects.keys()):
                obj_data = self.objects[obj_name]
                class_name = obj_data['class']
                attributes = obj_data['attributes']

                if class_name not in self.classes:
                    object_creation_lines.append(f"    # Skipping object '{obj_name}': Class '{class_name}' not found.")
                    continue

                class_data = self.classes[class_name]
                # Pobierz wszystkie pola z łańcucha dziedziczenia
                all_fields = []
                parent = class_data.get('inherits')
                parents_chain = []
                while parent:
                    if parent in self.classes:
                        parents_chain.insert(0, self.classes[parent])
                        parent = self.classes[parent].get('inherits')
                    else:
                        break
                for pcd in parents_chain:
                    all_fields.extend(pcd.get('fields', []))
                all_fields.extend(class_data.get('fields', []))

                init_param_names = [f['name'] for f in all_fields]

                init_args = []
                for param_name in init_param_names:
                    value = attributes.get(param_name)
                    formatted_value = "None"
                    if value is not None:
                        is_ref = value in self.objects
                        if isinstance(value, str) and not is_ref:
                            formatted_value = repr(value)
                        elif isinstance(value, (int, float, bool)):
                            formatted_value = str(value)
                        elif is_ref:
                            formatted_value = value
                        else:
                            try:
                                formatted_value = repr(value)
                            except Exception:
                                formatted_value = f"'<Error formatting value for {param_name}>'"
                    init_args.append(f"{param_name}={formatted_value}")

                object_creation_lines.append(f"    {obj_name} = {class_name}({', '.join(init_args)})")

            code_lines.extend(object_creation_lines)

            code_lines.append("\n    # --- Example Usage (Optional) ---")
            if self.objects:
                first_obj_name = sorted(self.objects.keys())[0]
                code_lines.append(f"    # print(vars({first_obj_name}))")
            code_lines.append("    pass")

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

    def _create_object_creator_widget(self) -> QWidget:
        """Tworzy widget dla trybu tworzenia obiektów."""
        creator_widget = QWidget()
        creator_layout = QHBoxLayout(creator_widget) # Main layout: Left (Creation), Right (List)

        # --- Panel lewy: Tworzenie obiektu ---
        creation_panel = QWidget()
        creation_panel.setFixedWidth(400)
        creation_layout = QVBoxLayout(creation_panel)
        creation_layout.setContentsMargins(5, 5, 5, 5)
        creation_layout.setSpacing(10)

        creation_layout.addWidget(QLabel("<h2>Tworzenie Obiektu</h2>")) # Title

        # Wybór klasy i nazwa obiektu
        class_name_layout = QHBoxLayout()
        self.object_class_combo = QComboBox()
        self.object_class_combo.setPlaceholderText("Wybierz klasę...")
        self.object_class_combo.currentIndexChanged.connect(self._update_object_creation_form)
        class_name_layout.addWidget(QLabel("Klasa:"))
        class_name_layout.addWidget(self.object_class_combo)

        self.object_name_input = QLineEdit()
        self.object_name_input.setPlaceholderText("Nazwa nowego obiektu")
        class_name_layout.addWidget(QLabel("Nazwa:"))
        class_name_layout.addWidget(self.object_name_input)
        creation_layout.addLayout(class_name_layout)

        # Formularz atrybutów (w scroll area)
        creation_layout.addWidget(QLabel("Atrybuty obiektu:"))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.fields_form_widget = QWidget() # Widget inside scroll area
        self.object_fields_layout = QFormLayout(self.fields_form_widget) # Form layout for fields
        self.object_fields_layout.setContentsMargins(5, 5, 5, 5)
        self.object_fields_layout.setSpacing(8)
        self.scroll_area.setWidget(self.fields_form_widget)
        creation_layout.addWidget(self.scroll_area)

        # Przyciski
        self.create_object_btn = QPushButton("Utwórz Obiekt")
        self.create_object_btn.clicked.connect(self.create_object)
        creation_layout.addWidget(self.create_object_btn)
        creation_layout.addStretch()

        # --- Panel prawy: Lista obiektów ---
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(5,5,5,5)
        list_layout.setSpacing(10)

        list_layout.addWidget(QLabel("<h2>Istniejące Obiekty</h2>"))
        self.object_tree = QTreeWidget()
        self.object_tree.setHeaderLabel("Obiekty")
        self.object_tree.setColumnCount(2) # Columns for Attribute, Value
        self.object_tree.setHeaderLabels(["Nazwa / Atrybut", "Wartość"])
        self.object_tree.setColumnWidth(0, 200) # Adjust column width
        list_layout.addWidget(self.object_tree)
        
        self.delete_object_btn = QPushButton("Usuń zaznaczony obiekt")
        self.delete_object_btn.clicked.connect(self.delete_object)
        list_layout.addWidget(self.delete_object_btn)

        # --- Dodanie paneli do głównego layoutu kreatora ---
        creator_layout.addWidget(creation_panel)
        creator_layout.addWidget(list_panel)

        return creator_widget

    def _switch_mode(self):
        """Przełącza między trybem edycji klas a tworzenia obiektów."""
        current_index = self.stacked_widget.currentIndex()
        if current_index == 0: # Currently in class editor
            self.stacked_widget.setCurrentIndex(1)
            self.mode_switch_button.setText("Przejdź do edycji klas")
            self._update_object_class_combo() # Ensure combo is up-to-date
            self._update_object_tree()       # Ensure tree is up-to-date
            self._update_object_creation_form() # Update form based on current selection
        else: # Currently in object creator
            self.stacked_widget.setCurrentIndex(0)
            self.mode_switch_button.setText("Przejdź do tworzenia obiektów")
            # No specific update needed for class editor on switch back (it retains state)

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
        self.classes_changed.emit() # Notify object creator UI

    def delete_class(self):
        """Usuwa wybraną klasę z diagramu (i powiązane obiekty)"""
        current_selection = self.editor_class_list.currentItem()
        if not current_selection:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy do usunięcia!")
            return
        class_to_delete = current_selection.text()

        # Confirmation dialog including object deletion warning
        objects_of_this_class = [name for name, data in self.objects.items() if data['class'] == class_to_delete]
        warning_msg = ""
        if objects_of_this_class:
            warning_msg = f"\n\nUWAGA: Usunięcie tej klasy spowoduje również usunięcie {len(objects_of_this_class)} obiektów tej klasy: {', '.join(objects_of_this_class[:5])}{'...' if len(objects_of_this_class) > 5 else ''}."

        reply = QMessageBox.question(self, "Potwierdzenie usunięcia klasy",
                                     f"Czy na pewno chcesz usunąć klasę '{class_to_delete}' "
                                     f"oraz wszystkie powiązane z nią relacje?{warning_msg}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        # --- Delete objects of this class first ---
        objects_to_delete = list(objects_of_this_class) # Copy list as we modify dict
        for obj_name in objects_to_delete:
             self._remove_object_internal(obj_name) # Use internal helper

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
            
        # --- Clean up object attributes referencing deleted class objects ---
        # (This is implicitly handled by deleting the objects first)

        # --- Update UI ---
        if self.selected_class_editor == class_to_delete:
            self.selected_class_editor = None
            self.editor_class_list.setCurrentItem(None)
            # Disable panels if no class is selected
            self._enable_editor_panels(False)

        self._update_all_class_editor_views()
        self.classes_changed.emit() # Notify object creator UI
        self.objects_changed.emit() # Notify object creator UI about deleted objects


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

        field_type = self.editor_field_type_combo.currentText()

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


    # --- Metody logiki biznesowej (obiekty) ---

    def create_object(self):
        """Tworzy nowy obiekt na podstawie wybranej klasy i formularza."""
        selected_class_name = self.object_class_combo.currentText()
        object_name = self.object_name_input.text().strip()

        if not selected_class_name:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy do utworzenia obiektu.")
            return
        if not object_name:
            QMessageBox.warning(self, "Błąd", "Nazwa obiektu nie może być pusta.")
            return
        if object_name in self.objects:
            QMessageBox.warning(self, "Błąd", f"Obiekt o nazwie '{object_name}' już istnieje.")
            return

        attributes = {}
        try:
            for field_name, input_widget in self._object_input_widgets:
                if isinstance(input_widget, QLineEdit):
                    attributes[field_name] = input_widget.text()
                elif isinstance(input_widget, QComboBox):
                    # Store the selected object name, or None if "(Brak)" is selected
                    value = input_widget.currentText()
                    attributes[field_name] = None if value == "(Brak)" else value
                # Add more type handling here if needed (e.g., QSpinBox, QCheckBox)
        except Exception as e:
             QMessageBox.critical(self,"Błąd odczytu atrybutów", f"Wystąpił błąd podczas odczytywania wartości pól: {e}")
             return

        # Store the object
        self.objects[object_name] = {
            'class': selected_class_name,
            'attributes': attributes
        }

        # --- Update UI ---
        self.object_name_input.clear()
        # Don't clear the class combo, maybe clear the form fields?
        self._update_object_creation_form() # Rebuild form (clears previous values)
        self.objects_changed.emit() # Signal that objects have changed

        QMessageBox.information(self, "Sukces", f"Utworzono obiekt '{object_name}' klasy '{selected_class_name}'.")

    def delete_object(self):
        """Usuwa zaznaczony obiekt z listy."""
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do usunięcia.")
            return
            
        # Ensure a top-level item (object name) is selected
        item = selected_items[0]
        while item.parent(): # Navigate up to the root item
            item = item.parent()
            
        object_name = item.text(0) # Get object name from top-level item

        if object_name not in self.objects:
             QMessageBox.warning(self, "Błąd", f"Nie znaleziono obiektu '{object_name}' w danych.")
             return

        reply = QMessageBox.question(self, "Potwierdzenie usunięcia obiektu",
                                     f"Czy na pewno chcesz usunąć obiekt '{object_name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        # Internal removal and update
        self._remove_object_internal(object_name)
        self.objects_changed.emit()
        
    def _remove_object_internal(self, object_name: str):
        """Internal helper to remove object and update dependencies (without signals)."""
        if object_name not in self.objects:
            return

        # Remove the object itself
        del self.objects[object_name]

        # --- Nullify references in other objects ---
        # Go through all other objects and their attributes
        for other_obj_name, other_obj_data in self.objects.items():
            for attr_name, attr_value in other_obj_data['attributes'].items():
                if attr_value == object_name: # If an attribute referenced the deleted object
                    # Set the reference to None (or handle based on composition rules)
                    other_obj_data['attributes'][attr_name] = None
                    print(f"DEBUG: Set attribute '{attr_name}' of object '{other_obj_name}' to None (was '{object_name}')")

    # --- Metody aktualizacji UI Kreatora Obiektów ---

    def _update_object_creator_view(self):
        """Aktualizuje cały widok kreatora obiektów."""
        self._update_object_class_combo()
        self._update_object_creation_form() # Depends on combo selection
        self._update_object_tree()

    def _update_object_class_combo(self):
        """Aktualizuje listę klas w ComboBoxie do tworzenia obiektów."""
        current_selection = self.object_class_combo.currentText()
        self.object_class_combo.blockSignals(True) # Prevent triggering update form prematurely
        self.object_class_combo.clear()
        sorted_class_names = sorted(self.classes.keys())
        self.object_class_combo.addItems([""] + sorted_class_names) # Add empty option first
        self.object_class_combo.setPlaceholderText("Wybierz klasę...")

        index = self.object_class_combo.findText(current_selection)
        if index != -1:
             self.object_class_combo.setCurrentIndex(index)
        else:
             self.object_class_combo.setCurrentIndex(0) # Select empty/placeholder
        self.object_class_combo.blockSignals(False)
        
        # Trigger form update manually IF a valid class was previously selected or is now selected
        if self.object_class_combo.currentIndex() > 0:
             self._update_object_creation_form()
        else:
            self._clear_object_creation_form() # Clear if no class selected

    def _clear_object_creation_form(self):
         # Clear previous widgets from layout
        while self.object_fields_layout.count():
            child = self.object_fields_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._object_input_widgets = [] # Clear widget references
        self.create_object_btn.setEnabled(False) # Disable button


    def _update_object_creation_form(self):
        """Aktualizuje formularz do wprowadzania atrybutów obiektu."""
        self._clear_object_creation_form() # Clear previous form first

        selected_class_name = self.object_class_combo.currentText()
        if not selected_class_name or selected_class_name not in self.classes:
            return # Nothing to build

        # Get all fields (own and inherited)
        all_fields_data = self._get_all_fields_recursive(selected_class_name)
        if not all_fields_data:
             # Add a label indicating no fields if necessary
             self.object_fields_layout.addRow(QLabel("Brak pól do wypełnienia."), QLabel(""))
             self.create_object_btn.setEnabled(True) # Can still create object if no fields
             return

        # Sort fields for consistent order
        all_fields_data.sort(key=lambda x: (x['source'] != selected_class_name, x['field']['name'])) # Own fields first, then alphabetical


        for field_info in all_fields_data:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']
            source_class = field_info['source']

            label_text = f"{field_name} ({field_type})"
            if source_class != selected_class_name:
                label_text += f" [z {source_class}]"
            field_label = QLabel(label_text)

            input_widget = None

            # --- Determine Input Widget Type ---
            is_composition = field_type in self.classes and self._is_composition_field(field_name, field_type, self.classes[source_class].get('compositions', []))

            if is_composition:
                # Use ComboBox for composition
                combo = QComboBox()
                combo.addItem("(Brak)") # Option for no object assigned
                # Find existing objects of the required type (field_type)
                compatible_objects = sorted([
                    name for name, data in self.objects.items() if data['class'] == field_type
                ])
                combo.addItems(compatible_objects)
                input_widget = combo
                self._object_input_widgets.append((field_name, combo))
            # Add elif for other specific types (bool -> QCheckBox, int -> QSpinBox etc.) if desired
            # elif field_type == "int": ...
            else:
                # Default to QLineEdit for str, list, dict, float, unknown, etc.
                line_edit = QLineEdit()
                input_widget = line_edit
                self._object_input_widgets.append((field_name, line_edit))

            self.object_fields_layout.addRow(field_label, input_widget)
        
        self.create_object_btn.setEnabled(True) # Enable button once form is built


    def _update_object_tree(self):
        """Aktualizuje drzewo obiektów."""
        self.object_tree.clear()
        bold_font = QFont()
        bold_font.setBold(True)

        for obj_name in sorted(self.objects.keys()):
            obj_data = self.objects[obj_name]
            class_name = obj_data['class']

            obj_item = QTreeWidgetItem([obj_name])
            obj_item.setFont(0, bold_font) # Make object name bold
            self.object_tree.addTopLevelItem(obj_item)

            # Add class info
            class_item = QTreeWidgetItem(["Klasa", class_name])
            obj_item.addChild(class_item)

            # Add attributes
            attributes_node = QTreeWidgetItem(["Atrybuty", ""])
            obj_item.addChild(attributes_node)
            
            if not obj_data['attributes']:
                 no_attr_item = QTreeWidgetItem(["(brak zdefiniowanych atrybutów)", ""])
                 attributes_node.addChild(no_attr_item)
            else:
                for attr_name in sorted(obj_data['attributes'].keys()):
                    attr_value = obj_data['attributes'][attr_name]
                    # Display None as "(Brak)" or similar
                    display_value = str(attr_value) if attr_value is not None else "(Brak)" 
                    attr_item = QTreeWidgetItem([f"  {attr_name}", display_value])
                    attributes_node.addChild(attr_item)

        self.object_tree.expandAll()


    def _update_composition_combos(self):
        """Updates QComboBoxes in the object creation form when the list of objects changes."""
        # This is slightly tricky as the form rebuilds anyway on class change.
        # But if we are *on* the form and an object is created/deleted, existing combos
        # for composition need updating.
        
        # Iterate through the currently displayed input widgets
        for field_name, widget in self._object_input_widgets:
             if isinstance(widget, QComboBox):
                 # Check if this combo represents a composition (based on its contents perhaps?)
                 # A simpler check: assume any QComboBox in the form is for composition
                 # We need the *type* this combo is for. Find it from the current class fields.
                 current_class_name = self.object_class_combo.currentText()
                 if not current_class_name: continue
                 
                 all_fields = self._get_all_fields_recursive(current_class_name)
                 field_data = next((f['field'] for f in all_fields if f['field']['name'] == field_name), None)
                 
                 if field_data and field_data['type'] in self.classes:
                      field_type = field_data['type']
                      current_combo_selection = widget.currentText()
                      
                      widget.blockSignals(True)
                      widget.clear()
                      widget.addItem("(Brak)")
                      compatible_objects = sorted([
                          name for name, data in self.objects.items() if data['class'] == field_type
                      ])
                      widget.addItems(compatible_objects)
                      
                      # Try to restore selection
                      index = widget.findText(current_combo_selection)
                      if index != -1:
                          widget.setCurrentIndex(index)
                      else:
                          widget.setCurrentIndex(0) # Default to (Brak)
                          
                      widget.blockSignals(False)




if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ClassDiagramEditor()
    window.show()
    sys.exit(app.exec())