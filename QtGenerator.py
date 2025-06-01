import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,QComboBox, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QFormLayout, QScrollArea,
    QSpinBox, QCheckBox, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QStackedWidget
)
from PyQt6.QtCore import pyqtSignal, QLocale, Qt
from PyQt6.QtGui import QDoubleValidator
from typing import Dict, List, Optional, Any, Tuple
import random
import string
import importlib
import inspect
import ast
import textwrap
# --- Type Definitions (Optional but good practice) ---
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any]
ObjectsDict = Dict[str, Any] # Stores actual Python objects


# --- Dialog for Connecting Objects ---
# --- Dialog for Connecting Objects ---
class ConnectObjectsDialog(QDialog):
    def __init__(self, objects_dict: ObjectsDict, classes_dict: ClassesDict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Połącz Obiekty")
        self.objects = objects_dict
        self.classes = classes_dict
        # Removed self.target_object, self.target_attribute, self.source_object as they are determined on accept

        layout = QVBoxLayout(self)
        self.form_layout = QFormLayout() # Make form_layout accessible

        # 1. Select Target Object
        self.target_object_combo = QComboBox()
        self.target_object_combo.addItem("-- Wybierz obiekt docelowy --")
        self.target_object_combo.addItems(sorted(self.objects.keys()))
        self.target_object_combo.currentIndexChanged.connect(self._update_target_attributes)
        self.form_layout.addRow("Obiekt docelowy:", self.target_object_combo)

        # 2. Select Target Attribute (filtered for composition)
        self.target_attribute_combo = QComboBox()
        self.target_attribute_combo.setEnabled(False) # Enable when target is selected
        self.target_attribute_combo.currentIndexChanged.connect(self._update_source_widgets) # Changed method name
        self.form_layout.addRow("Atrybut docelowy:", self.target_attribute_combo)

        # 3. Select Source Object(s) using QStackedWidget
        self.source_stacked_widget = QStackedWidget()
        self.source_object_combo = QComboBox() # For single selection
        self.source_objects_list_widget = QListWidget() # For multi-selection
        self.source_objects_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self.source_stacked_widget.addWidget(self.source_object_combo)       # Index 0
        self.source_stacked_widget.addWidget(self.source_objects_list_widget) # Index 1
        self.source_stacked_widget.setEnabled(False) # Disable stack itself initially
        self.form_layout.addRow("Obiekt(y) źródłowe:", self.source_stacked_widget)

        layout.addLayout(self.form_layout)

        # To store type of connection for get_connection_details
        self._current_attribute_is_list = False

        # OK and Cancel buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _parse_field_type(self, type_str: str) -> Tuple[str, List[str]]:
        """Parsuje typ pola i zwraca krotkę (base_type, type_arguments)."""
        # Ensure we handle cases like 'wygenerowany_kod.Klasa' becoming 'Klasa' if not generic
        # and 'typing.List[wygenerowany_kod.Klasa]' having base 'typing.List'
        if '[' not in type_str or ']' not in type_str:
            return type_str.split('.')[-1], [] # Return base name for non-generics

        base_type_full = type_str[:type_str.find('[')] # e.g. typing.List
        content = type_str[type_str.find('[')+1:type_str.rfind(']')]

        args = []
        current_arg = ""
        nest_level = 0
        for char in content:
            if char == '[':
                nest_level += 1
                current_arg += char
            elif char == ']':
                nest_level -= 1
                current_arg += char
            elif char == ',' and nest_level == 0:
                args.append(current_arg.strip())
                current_arg = ""
            else:
                current_arg += char
        if current_arg:
            args.append(current_arg.strip())
        
        return base_type_full, args


    def _get_connectable_field_info(self, field_type_str: str) -> Tuple[Optional[str], bool]:
        """
        Determines if a field type is connectable and what kind of connection.
        Returns: (connectable_class_name_or_None, is_list_of_that_class)
        """
        base_type_full, type_args = self._parse_field_type(field_type_str)
        base_type_simple = base_type_full.split('.')[-1] # e.g., List, Optional, MyClass

        if base_type_simple in self.classes: # Direct class reference e.g. "MyClass"
            return base_type_simple, False

        if base_type_simple.lower() in ['list', 'sequence']:
            if type_args:
                item_type_arg_str = type_args[0].strip("'\" ") # e.g. "MyClass" or "module.MyClass"
                cleaned_item_type = item_type_arg_str.split('.')[-1]
                if cleaned_item_type in self.classes:
                    return cleaned_item_type, True
            return None, False

        if base_type_simple.lower() in ['optional', 'union']:
            for arg_str in type_args:
                if arg_str.strip().lower() not in ['none', 'nonetype', 'type[none]']:
                    connectable_class, is_list = self._get_connectable_field_info(arg_str)
                    if connectable_class:
                        return connectable_class, is_list
            return None, False

        return None, False

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        if class_name not in self.classes: return []
        if visited is None: visited = set()
        if class_name in visited: return []
        visited.add(class_name)
        fields_map = {}
        parent_class_name = self.classes[class_name].get('inherits')
        if parent_class_name and parent_class_name in self.classes:
            parent_fields = self._get_all_fields_recursive(parent_class_name, visited.copy())
            for field_info in parent_fields:
                fields_map[field_info['field']['name']] = field_info
        own_fields = self.classes[class_name].get('fields', [])
        for field_data in own_fields:
            fields_map[field_data['name']] = {'field': field_data, 'source_class': class_name}
        return list(fields_map.values())

    def _is_composition_field(self, field_name: str) -> bool:
        return field_name.startswith('composed_')

    def _get_composition_target_class(self, field_name: str) -> Optional[str]:
        if not self._is_composition_field(field_name): return None
        parts = field_name.split('_')
        if len(parts) >= 2:
            potential_class_identifier = parts[1]
            for actual_class_name in self.classes.keys():
                if actual_class_name.lower() == potential_class_identifier.lower():
                    return actual_class_name
            if potential_class_identifier in self.classes: # Fallback for exact match
                 return potential_class_identifier
        return None

    def _update_target_attributes(self):
        self.target_attribute_combo.clear()
        self.target_attribute_combo.setEnabled(False)
        self._update_source_widgets() # Clear and disable source widgets

        target_obj_name = self.target_object_combo.currentText()
        if not target_obj_name or target_obj_name.startswith("--"):
            return

        target_obj = self.objects.get(target_obj_name)
        if not target_obj:
            self.target_attribute_combo.addItem("-- Obiekt docelowy nie istnieje --")
            return

        target_class_name = target_obj.__class__.__name__
        if target_class_name not in self.classes:
            self.target_attribute_combo.addItem("-- Klasa obiektu nieznana --")
            return

        compatible_attributes = []
        all_fields_info = self._get_all_fields_recursive(target_class_name)

        for field_info_item in all_fields_info:
            field_data = field_info_item['field']
            field_name = field_data['name']
            field_type_str = field_data['type']

            if self._is_composition_field(field_name):
                target_class_for_composed = self._get_composition_target_class(field_name)
                if target_class_for_composed and target_class_for_composed in self.classes:
                    compatible_attributes.append(field_name)
            else:
                connectable_class, _ = self._get_connectable_field_info(field_type_str)
                if connectable_class:
                    compatible_attributes.append(field_name)
        
        if compatible_attributes:
            self.target_attribute_combo.addItem("-- Wybierz atrybut --")
            self.target_attribute_combo.addItems(sorted(compatible_attributes))
            self.target_attribute_combo.setEnabled(True)
        else:
            self.target_attribute_combo.addItem("-- Brak atrybutów obiektowych --")

    def _update_source_widgets(self): # Renamed from _update_source_objects
        """Updates the source selection widget (combo or list) based on the target attribute."""
        self.source_stacked_widget.setEnabled(False)
        self.source_object_combo.clear()
        self.source_objects_list_widget.clear()
        self._current_attribute_is_list = False # Reset

        target_obj_name = self.target_object_combo.currentText()
        attribute_name = self.target_attribute_combo.currentText()

        if (not target_obj_name or target_obj_name.startswith("--") or
            not attribute_name or attribute_name.startswith("--")):
            # Add placeholder to current widget in stack and disable
            current_widget = self.source_stacked_widget.currentWidget()
            if isinstance(current_widget, QComboBox):
                current_widget.addItem("-- Najpierw wybierz atrybut --")
            elif isinstance(current_widget, QListWidget):
                current_widget.addItem("-- Najpierw wybierz atrybut --")
            return

        target_obj = self.objects[target_obj_name]
        target_class_name_actual = target_obj.__class__.__name__
        
        expected_item_class = None
        
        all_fields_info = self._get_all_fields_recursive(target_class_name_actual)
        field_definition_found = False
        for field_info_item in all_fields_info:
            field_data = field_info_item['field']
            if field_data['name'] == attribute_name:
                field_type_str = field_data['type']
                if self._is_composition_field(attribute_name):
                    expected_item_class = self._get_composition_target_class(attribute_name)
                    self._current_attribute_is_list = False
                else:
                    conn_class, is_list = self._get_connectable_field_info(field_type_str)
                    if conn_class:
                        expected_item_class = conn_class
                        self._current_attribute_is_list = is_list
                field_definition_found = True
                break
        
        if not field_definition_found or not expected_item_class:
            # This case should ideally be prevented by _update_target_attributes
            current_widget = self.source_stacked_widget.currentWidget()
            msg = "-- Błąd: Nie można określić typu docelowego --"
            if isinstance(current_widget, QComboBox): current_widget.addItem(msg)
            else: current_widget.addItem(QListWidgetItem(msg))
            print(f"Could not determine target type for {target_obj_name}.{attribute_name}")
            return

        # Filter compatible source objects
        compatible_sources = []
        for obj_name, obj_instance in self.objects.items():
            if obj_name == target_obj_name: # Cannot connect to self in this way
                continue
            if obj_instance.__class__.__name__ == expected_item_class:
                compatible_sources.append(obj_name)
        
        compatible_sources.sort()

        if self._current_attribute_is_list:
            self.source_stacked_widget.setCurrentWidget(self.source_objects_list_widget)
            if compatible_sources:
                for src_name in compatible_sources:
                    self.source_objects_list_widget.addItem(QListWidgetItem(src_name))
                self.source_stacked_widget.setEnabled(True)
                self.source_objects_list_widget.setEnabled(True)
            else:
                item = QListWidgetItem(f"-- Brak obiektów typu {expected_item_class} --")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
                self.source_objects_list_widget.addItem(item)
                self.source_stacked_widget.setEnabled(True) # Stack itself can be enabled
                self.source_objects_list_widget.setEnabled(False) # But list is not usable
        else: # Single object connection
            self.source_stacked_widget.setCurrentWidget(self.source_object_combo)
            if compatible_sources:
                self.source_object_combo.addItem("-- Wybierz obiekt źródłowy --")
                self.source_object_combo.addItems(compatible_sources)
                self.source_stacked_widget.setEnabled(True)
                self.source_object_combo.setEnabled(True)
            else:
                self.source_object_combo.addItem(f"-- Brak obiektów typu {expected_item_class} --")
                self.source_stacked_widget.setEnabled(True)
                self.source_object_combo.setEnabled(False)


    def get_connection_details(self) -> Optional[Tuple[str, str, Any]]: # Any can be str or List[str]
        target_obj_name = self.target_object_combo.currentText()
        attribute_name = self.target_attribute_combo.currentText()

        if target_obj_name.startswith("--") or attribute_name.startswith("--"):
            return None

        source_data: Any = None
        if self._current_attribute_is_list:
            if self.source_stacked_widget.currentWidget() == self.source_objects_list_widget:
                selected_items = self.source_objects_list_widget.selectedItems()
                # Filter out any non-selectable placeholder items
                source_data = [item.text() for item in selected_items if item.flags() & Qt.ItemFlag.ItemIsSelectable]
            else: return None # Should not happen
        else: # Single object
            if self.source_stacked_widget.currentWidget() == self.source_object_combo:
                source_data = self.source_object_combo.currentText()
                if source_data.startswith("--"): # No valid single object selected
                    return None
            else: return None # Should not happen
        
        if source_data is None: # Catch all for safety
             return None

        return target_obj_name, attribute_name, source_data
# --- Main Application Window ---
class ObjectGeneratorApp(QMainWindow):
    objects_changed = pyqtSignal()

    def __init__(self, classes_module):
        super().__init__()
        self.setWindowTitle("Generator Obiektów")
        self.setGeometry(100, 100, 1000, 700)

        self.classes_module = classes_module
        self.classes = self._analyze_classes(classes_module)
        self.objects: ObjectsDict = {}  # Stores actual Python objects
        self.object_data = {}  # Stores metadata about objects (class, attributes)

        self._setup_ui()
        self._update_object_class_combo()
        self._update_object_creation_form()  # Initialize the form
        self._update_object_tree()

        # Connect signals
        self.objects_changed.connect(self._update_object_tree)
        self.objects_changed.connect(self._update_composition_combos)

    def _analyze_classes(self, module) -> ClassesDict:
        """Analyzes the module and extracts class information."""
        classes = {}
        module_name = module.__name__

        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and getattr(obj, '__module__', None) == module_name:
                parent = None
                try:
                    for base in obj.__bases__:
                        if getattr(base, '__module__', None) == module_name and base is not object:
                            parent = base.__name__
                            break
                except AttributeError:
                    pass

                fields = []
                composition_fields = []

                try:
                    # Analizuj konstruktor
                    init_sig = inspect.signature(obj.__init__)
                    source_code = inspect.getsource(obj.__init__)

                    # Znajdź kompozycje w kodzie konstruktora
                    composition_fields = self._extract_composition_from_constructor(source_code, module_name)

                    for param_name, param in init_sig.parameters.items():
                        if param_name == 'self':
                            continue

                        param_type_str = "Any"
                        annotation = param.annotation

                        if annotation != inspect.Parameter.empty:
                            if isinstance(annotation, str):
                                param_type_str = annotation
                            elif hasattr(annotation, '__name__'):
                                param_type_str = annotation.__name__
                            elif hasattr(annotation, '__origin__'):
                                origin = annotation.__origin__
                                origin_name = getattr(origin, '__name__', str(origin))
                                args = getattr(annotation, '__args__', [])
                                arg_names = []
                                for arg in args:
                                    if isinstance(arg, type(None)):
                                        arg_names.append('NoneType')
                                    elif hasattr(arg, '__name__'):
                                        arg_names.append(arg.__name__)
                                    elif isinstance(arg, str):
                                        arg_names.append(arg)
                                    else:
                                        arg_names.append(str(arg))
                                param_type_str = f"{origin_name}[{', '.join(arg_names)}]"
                            else:
                                param_type_str = str(annotation).replace(f"{module_name}.", "")
                        elif param.default != inspect.Parameter.empty and param.default is not None:
                            param_type_str = type(param.default).__name__

                        fields.append({"name": param_name, "type": param_type_str})

                    # Dodaj pola kompozycji
                    fields.extend(composition_fields)

                except (ValueError, TypeError, AttributeError):
                    try:
                        annotations = inspect.get_annotations(obj, eval_str=True)
                        existing_field_names = {f['name'] for f in fields}
                        for attr_name, attr_type in annotations.items():
                            if not attr_name.startswith('_') and attr_name not in existing_field_names:
                                type_name = "Any"
                                if hasattr(attr_type, '__name__'):
                                    type_name = attr_type.__name__
                                elif hasattr(attr_type, '__origin__'):
                                    origin = attr_type.__origin__
                                    origin_name = getattr(origin, '__name__', str(origin))
                                    args = getattr(attr_type, '__args__', [])
                                    arg_names = []
                                    for arg in args:
                                        if isinstance(arg, type(None)):
                                            arg_names.append('NoneType')
                                        elif hasattr(arg, '__name__'):
                                            arg_names.append(arg.__name__)
                                        else:
                                            arg_names.append(str(arg))
                                    type_name = f"{origin_name}[{', '.join(arg_names)}]"
                                else:
                                    type_name = str(attr_type).replace(f"{module_name}.", "")
                                fields.append({"name": attr_name, "type": type_name})
                    except Exception as e_annot:
                        print(f"Debug: Could not process annotations for {name}: {e_annot}")

                classes[name] = {
                    "fields": fields,
                    "inherits": parent,
                    "class_obj": obj
                }

        return classes

    import textwrap

    def _extract_composition_from_constructor(self, source_code: str, module_name: str) -> List[Dict[str, str]]:
        """Wyciąga kompozycje z kodu konstruktora."""
        composition_fields = []

        try:
            # Usuń wcięcia z kodu źródłowego
            dedented_code = textwrap.dedent(source_code)

            # Jeśli kod nadal ma problemy z wcięciami, użyj workaround
            lines = dedented_code.split('\n')
            if lines and lines[0].strip().startswith('def '):
                # Kod już jest poprawnie sformatowany
                clean_code = dedented_code
            else:
                # Dodaj dummy wrapper dla wcięć
                clean_code = "if True:\n" + textwrap.indent(dedented_code, "    ")

            # Parsuj kod źródłowy
            tree = ast.parse(clean_code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    # Szukaj przypisań typu self.attr = ClassName(...)
                    for target in node.targets:
                        if (isinstance(target, ast.Attribute) and
                                isinstance(target.value, ast.Name) and
                                target.value.id == 'self'):

                            attr_name = target.attr

                            # Sprawdź czy wartość to wywołanie konstruktora
                            if isinstance(node.value, ast.Call):
                                class_name = None
                                if isinstance(node.value.func, ast.Name):
                                    class_name = node.value.func.id
                                elif isinstance(node.value.func, ast.Attribute):
                                    # Obsługa module.ClassName
                                    if hasattr(node.value.func, 'attr'):
                                        class_name = node.value.func.attr

                                if class_name and class_name in self.classes:
                                    composition_fields.append({
                                        "name": attr_name,
                                        "type": class_name
                                    })
        except Exception as e:
            print(f"Błąd podczas analizy kompozycji: {e}")

        return composition_fields

    def _setup_ui(self):
        """Configures the main user interface."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # --- Left Panel: Object Creation ---
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout(left_panel)

        # Class selection
        class_layout = QHBoxLayout()
        class_layout.addWidget(QLabel("Klasa:"))
        self.object_class_combo = QComboBox()
        self.object_class_combo.currentIndexChanged.connect(self._update_object_creation_form)
        class_layout.addWidget(self.object_class_combo)
        left_layout.addLayout(class_layout)

        # Object name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nazwa obiektu:"))
        self.object_name_input = QLineEdit()
        name_layout.addWidget(self.object_name_input)
        left_layout.addLayout(name_layout)

        # Attributes form
        left_layout.addWidget(QLabel("Atrybuty:"))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.fields_form_widget = QWidget()
        self.object_fields_layout = QFormLayout(self.fields_form_widget)
        self.object_fields_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_area.setWidget(self.fields_form_widget)
        left_layout.addWidget(self.scroll_area)

        # Generate random data button
        self.generate_data_btn = QPushButton("Wygeneruj losowe dane")
        self.generate_data_btn.clicked.connect(self._generate_random_data)
        left_layout.addWidget(self.generate_data_btn)

        # Create/Update object button
        self.create_update_object_btn = QPushButton("Utwórz/Zaktualizuj obiekt") # Renamed variable
        self.create_update_object_btn.clicked.connect(self._create_or_update_object)
        left_layout.addWidget(self.create_update_object_btn)

        # Add button for creating predefined objects
        self.create_predefined_btn = QPushButton("Utwórz przykładowe obiekty")
        self.create_predefined_btn.clicked.connect(self._create_predefined_objects)
        left_layout.addWidget(self.create_predefined_btn)

        # --- Right Panel: Object List & Actions ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Istniejące obiekty:"))
        self.object_tree = QTreeWidget()
        self.object_tree.setHeaderLabels(["Właściwość", "Wartość"])
        self.object_tree.setColumnWidth(0, 200)
        right_layout.addWidget(self.object_tree)

        # Object actions buttons
        btn_layout = QHBoxLayout()
        self.edit_object_btn = QPushButton("Edytuj zaznaczony")
        self.edit_object_btn.clicked.connect(self._edit_selected_object)
        btn_layout.addWidget(self.edit_object_btn)

        self.delete_object_btn = QPushButton("Usuń zaznaczony")
        self.delete_object_btn.clicked.connect(self._delete_selected_object)
        btn_layout.addWidget(self.delete_object_btn)

        self.connect_objects_btn = QPushButton("Połącz Obiekty")
        self.connect_objects_btn.clicked.connect(self._show_connect_objects_dialog)
        btn_layout.addWidget(self.connect_objects_btn)

        # Renamed variable to avoid conflict with the create button on the left
        self.save_mongodb_btn = QPushButton("MongoDB")
        self.save_mongodb_btn.clicked.connect(self._save_objects_to_mongodb) # Connect to the correct method
        btn_layout.addWidget(self.save_mongodb_btn)

        self.save_mongodb_btn = QPushButton("Cassandra")
        self.save_mongodb_btn.clicked.connect(self._save_objects_to_cassandra)  # Connect to the correct method
        btn_layout.addWidget(self.save_mongodb_btn)

        self.save_mongodb_btn = QPushButton("Neo4j")
        self.save_mongodb_btn.clicked.connect(self._save_objects_to_neo4j)  # Connect to the correct method
        btn_layout.addWidget(self.save_mongodb_btn)
        right_layout.addLayout(btn_layout)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

    def _update_object_class_combo(self):
        """Updates the class selection ComboBox."""
        self.object_class_combo.clear()
        self.object_class_combo.addItems(sorted(self.classes.keys()))
        self.object_class_combo.setCurrentIndex(-1) # Start with no selection

    def _clear_layout(self, layout):
        """Recursively clear all items from a layout."""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    self._clear_layout(sub_layout)

    def _update_object_creation_form(self):
        """Updates the object creation form based on the selected class."""
        self._clear_layout(self.object_fields_layout)

        selected_class = self.object_class_combo.currentText()
        if not selected_class or selected_class not in self.classes:
            if selected_class:
                self.object_fields_layout.addRow(QLabel(f"Klasa '{selected_class}' nieznana."))
            return

        all_fields = self._get_all_fields_recursive(selected_class)
        all_fields.sort(key=lambda x: x['field']['name'])

        # Grupuj pola kompozycji
        composition_groups = {}
        regular_fields = []

        for field_info in all_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']

            if field_type in self.classes:
                # To jest kompozycja - znajdź pola konstruktora tej klasy
                comp_class_fields = self._get_all_fields_recursive(field_type)
                if field_type not in composition_groups:
                    composition_groups[field_type] = {
                        'attribute_name': field_name,
                        'fields': comp_class_fields
                    }
            else:
                regular_fields.append(field_info)

        # Dodaj regularne pola
        for field_info in regular_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']

            label = QLabel(f"{field_name} ({field_type})")
            input_widget = self._create_input_widget(field_type)

            if input_widget:
                self.object_fields_layout.addRow(label, input_widget)

        # Dodaj pola kompozycji
        for comp_type, comp_info in composition_groups.items():
            # Dodaj separator dla kompozycji
            separator_label = QLabel(f"=== Kompozycja: {comp_info['attribute_name']} ({comp_type}) ===")
            font = separator_label.font()
            font.setBold(True)
            separator_label.setFont(font)
            self.object_fields_layout.addRow(separator_label)

            # Dodaj pola dla parametrów kompozycji
            for comp_field_info in comp_info['fields']:
                comp_field = comp_field_info['field']
                comp_field_name = comp_field['name']
                comp_field_type = comp_field['type']

                # Utwórz nazwę pola z prefiksem klasy
                prefixed_name = f"{comp_type.lower()}_{comp_field_name}"

                label = QLabel(f"{prefixed_name} ({comp_field_type})")
                input_widget = self._create_input_widget(comp_field_type)

                if input_widget:
                    self.object_fields_layout.addRow(label, input_widget)

    def _create_input_widget(self, field_type: str):
        """Tworzy odpowiedni widget dla danego typu pola."""
        if field_type in ["List[float]", "List[int]", "List[str]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"Wpisz listę jako Python literal (np. [1.0, 2.0] dla List[float])")
        elif field_type in ["Dict[str, str]", "Dict[str, int]", "Dict[str, float]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"Wpisz słownik jako Python literal (np. {{'klucz': wartość}})")
        elif field_type in ["Set[int]", "Set[float]", "Set[str]", "FrozenSet[int]", "FrozenSet[float]",
                            "FrozenSet[str]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"Wpisz zbiór jako Python literal (np. {{1, 2, 3}})")
        elif field_type == "float":
            input_widget = QLineEdit()
            validator = QDoubleValidator()
            validator.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
            input_widget.setValidator(validator)
        elif field_type == "int":
            input_widget = QSpinBox()
            input_widget.setRange(-2147483647, 2147483647)
        elif field_type == "bool":
            input_widget = QCheckBox()
        elif field_type == "str":
            input_widget = QLineEdit()
        elif field_type in self.classes:  # Composition
            input_widget = QComboBox()
            input_widget.addItem("(Brak)")
            for obj_name, obj_instance in self.objects.items():
                if obj_instance.__class__.__name__ == field_type:
                    input_widget.addItem(obj_name)
        else:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"(Typ: {field_type})")

        return input_widget

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        """Recursively gets all fields (own and inherited) for a class."""
        if class_name not in self.classes:
            # print(f"Warning: Class '{class_name}' not found in analyzed classes.")
            return []
        if visited is None: visited = set()
        if class_name in visited: return []
        visited.add(class_name)

        fields_map: Dict[str, Dict[str, Any]] = {}

        # Get fields from parent first
        parent_class_name = self.classes[class_name].get('inherits')
        if parent_class_name and parent_class_name in self.classes:
            parent_fields_info = self._get_all_fields_recursive(parent_class_name, visited.copy())
            for field_info in parent_fields_info:
                fields_map[field_info['field']['name']] = field_info
        # else:
            # if parent_class_name: print(f"Warning: Inherited class '{parent_class_name}' not found.")

        # Add/overwrite with own fields
        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
             fields_map[field['name']] = {'field': field, 'source_class': class_name}

        return list(fields_map.values())

    def _generate_random_data(self):
        """Generates random data for the currently selected class form."""
        selected_class = self.object_class_combo.currentText()
        if not selected_class or selected_class not in self.classes:
            QMessageBox.warning(self, "Błąd", "Nie wybrano prawidłowej klasy do generowania danych.")
            return

        if not self.object_name_input.text():
            random_name = f"{selected_class.lower()}_{''.join(random.choices(string.ascii_lowercase, k=4))}"
            self.object_name_input.setText(random_name)

        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not label_item or not field_item:
                continue

            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if not isinstance(label_widget, QLabel) or not field_widget:
                continue

            try:
                field_name = label_widget.text().split('(')[0].strip()
                field_type = label_widget.text().split('(')[1][:-1].strip()
            except Exception:
                continue

            # Generowanie losowych danych dla różnych typów
            if isinstance(field_widget, QLineEdit):
                if field_type == "List[float]":
                    field_widget.setText(str([round(random.uniform(0, 100), 2) for _ in range(3)]))
                elif field_type == "List[int]":
                    field_widget.setText(str([random.randint(1, 100) for _ in range(3)]))
                elif field_type == "List[str]":
                    field_widget.setText(str([''.join(random.choices(string.ascii_letters, k=5)) for _ in range(3)]))
                elif field_type == "Dict[str, str]":
                    field_widget.setText(
                        str({f"key_{i}": ''.join(random.choices(string.ascii_letters, k=5)) for i in range(2)}))
                elif field_type == "Dict[str, int]":
                    field_widget.setText(str({f"key_{i}": random.randint(1, 100) for i in range(2)}))
                elif field_type == "Dict[str, float]":
                    field_widget.setText(str({f"key_{i}": round(random.uniform(1, 100), 2) for i in range(2)}))
                elif field_type == "Dict[str, Klasa]":
                    # Znajdź istniejące obiekty klasy Klasa
                    klasa_objects = [name for name, obj in self.objects.items()
                                     if obj.__class__.__name__ == "Klasa"]
                    if klasa_objects:
                        field_widget.setText(str({f"key_{i}": random.choice(klasa_objects) for i in range(2)}))
                    else:
                        field_widget.setText("{}")  # Pusty słownik jeśli brak obiektów
                elif field_type in ["Set[int]", "FrozenSet[int]"]:
                    field_widget.setText(str({random.randint(1, 100) for _ in range(3)}))
                elif field_type in ["Set[float]", "FrozenSet[float]"]:
                    field_widget.setText(str({round(random.uniform(1, 100), 2) for _ in range(3)}))
                elif field_type in ["Set[str]", "FrozenSet[str]"]:
                    field_widget.setText(str({''.join(random.choices(string.ascii_letters, k=5)) for _ in range(3)}))
                elif field_type == "float":
                    field_widget.setText(f"{random.uniform(0, 100):.2f}")
                elif field_type == "str":
                    field_widget.setText(''.join(random.choices(string.ascii_letters + ' ', k=10)))
                else:
                    field_widget.setText("random_val")
            elif isinstance(field_widget, QSpinBox):
                field_widget.setValue(random.randint(field_widget.minimum(), min(field_widget.maximum(), 100)))
            elif isinstance(field_widget, QCheckBox):
                field_widget.setChecked(random.choice([True, False]))
            elif isinstance(field_widget, QComboBox):  # Composition
                if field_widget.count() > 1:
                    field_widget.setCurrentIndex(random.randint(1, field_widget.count() - 1))
                else:
                    field_widget.setCurrentIndex(0)

    def _create_predefined_objects(self):
        """Creates predefined objects for all available classes."""
        created_objects = []

        for class_name, class_info in self.classes.items():
            # Create 1-2 instances per class
            for i in range(1, 3):
                obj_name = f"{class_name.lower()}_{i}"
                if obj_name in self.objects:
                    continue  # Skip if name exists

                # Prepare constructor args
                constructor_args = {}
                fields_info = self._get_all_fields_recursive(class_name)

                for field_info in fields_info:
                    field = field_info['field']
                    field_name = field['name']
                    field_type = field['type']

                    # Generate appropriate value based on type
                    if field_type == "int":
                        constructor_args[field_name] = random.randint(1, 100)
                    elif field_type == "float":
                        constructor_args[field_name] = round(random.uniform(1, 100), 2)
                    elif field_type == "bool":
                        constructor_args[field_name] = random.choice([True, False])
                    elif field_type == "str":
                        constructor_args[field_name] = ''.join(random.choices(string.ascii_letters, k=10))
                    elif field_type.startswith("List["):
                        element_type = field_type[5:-1]
                        if element_type == "int":
                            constructor_args[field_name] = [random.randint(1, 100) for _ in range(3)]
                        elif element_type == "float":
                            constructor_args[field_name] = [round(random.uniform(1, 100), 2) for _ in range(3)]
                        elif element_type == "str":
                            constructor_args[field_name] = [''.join(random.choices(string.ascii_letters, k=5)) for _ in
                                                            range(3)]
                        else:  # List of objects
                            compatible_objects = [obj for name, obj in self.objects.items()
                                                  if obj.__class__.__name__ == element_type]
                            if compatible_objects:
                                constructor_args[field_name] = random.sample(compatible_objects,
                                                                             min(3, len(compatible_objects)))
                            else:
                                constructor_args[field_name] = []
                    elif field_type.startswith("Dict["):
                        key_type, value_type = field_type[5:-1].split(",")
                        key_type = key_type.strip()
                        value_type = value_type.strip()

                        if value_type in self.classes:  # Dict[str, Klasa]
                            compatible_objects = [name for name, obj in self.objects.items()
                                                  if obj.__class__.__name__ == value_type]
                            if compatible_objects:
                                constructor_args[field_name] = {
                                    f"key_{i}": random.choice(compatible_objects)
                                    for i in range(2)
                                }
                            else:
                                constructor_args[field_name] = {}
                        else:  # Dict[str, primitive]
                            if value_type == "int":
                                constructor_args[field_name] = {f"key_{i}": random.randint(1, 100) for i in range(2)}
                            elif value_type == "float":
                                constructor_args[field_name] = {f"key_{i}": round(random.uniform(1, 100), 2) for i in
                                                                range(2)}
                            elif value_type == "str":
                                constructor_args[field_name] = {
                                    f"key_{i}": ''.join(random.choices(string.ascii_letters, k=5)) for i in range(2)}
                            else:
                                constructor_args[field_name] = {}
                    elif field_type in self.classes:  # Single object reference
                        compatible_objects = [obj for name, obj in self.objects.items()
                                              if obj.__class__.__name__ == field_type]
                        if compatible_objects:
                            constructor_args[field_name] = random.choice(compatible_objects)
                    else:
                        constructor_args[field_name] = "default_value"

                # Create the object
                try:
                    obj = class_info['class_obj'](**constructor_args)
                    self.objects[obj_name] = obj
                    self.object_data[obj_name] = {
                        'class': class_name,
                        'attributes': constructor_args
                    }
                    created_objects.append(obj_name)
                except Exception as e:
                    print(f"Error creating {obj_name}: {e}")

        if created_objects:
            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces", f"Utworzono przykładowe obiekty: {', '.join(created_objects)}")
        else:
            QMessageBox.information(self, "Informacja",
                                    "Nie utworzono nowych obiektów (wszystkie klasy mają już instancje).")

    def _create_or_update_object(self):
        """Creates a new object or updates an existing one based on form data."""
        class_name = self.object_class_combo.currentText()
        object_name = self.object_name_input.text().strip()

        if not class_name or class_name not in self.classes:
            QMessageBox.warning(self, "Błąd", "Nie wybrano prawidłowej klasy.")
            return
        if not object_name:
            QMessageBox.warning(self, "Błąd", "Nazwa obiektu nie może być pusta.")
            return

        # Zbierz dane z formularza
        form_data = {}
        conversion_errors = []

        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not label_item or not field_item:
                continue

            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if not isinstance(label_widget, QLabel) or not field_widget:
                continue

            try:
                field_name = label_widget.text().split('(')[0].strip()
                field_type = label_widget.text().split('(')[1][:-1].strip()
            except Exception:
                continue

            # Pobierz wartość z widgetu
            value = None
            try:
                if isinstance(field_widget, QLineEdit):
                    text_value = field_widget.text()
                    if text_value:
                        if field_type == "int":
                            value = int(text_value)
                        elif field_type == "float":
                            value = float(text_value)
                        elif field_type == "str":
                            value = text_value
                        else:
                            value = text_value
                elif isinstance(field_widget, QSpinBox):
                    value = field_widget.value()
                elif isinstance(field_widget, QCheckBox):
                    value = field_widget.isChecked()

                form_data[field_name] = value
            except (ValueError, TypeError) as e:
                conversion_errors.append(f"Pole '{field_name}': {e}")

        if conversion_errors:
            QMessageBox.warning(self, "Błąd danych wejściowych", "Popraw błędy:\n\n" + "\n".join(conversion_errors))
            return

        # Przygotuj argumenty konstruktora z inteligentną analizą kompozycji
        constructor_args = self._prepare_constructor_args(class_name, form_data)

        try:
            if object_name in self.objects:  # Update
                # Dla aktualizacji, ustaw atrybuty bezpośrednio
                obj = self.objects[object_name]
                for attr_name, attr_value in constructor_args.items():
                    setattr(obj, attr_name, attr_value)
            else:  # Create new
                obj = self.classes[class_name]['class_obj'](**constructor_args)
                self.objects[object_name] = obj
                self.object_data[object_name] = {'class': class_name, 'attributes': constructor_args.copy()}

            self.object_name_input.clear()
            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces",
                                    f"Obiekt '{object_name}' {'zaktualizowany' if object_name in self.objects else 'utworzony'}.")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć/zaktualizować obiektu: {e}")

    def _prepare_constructor_args(self, class_name: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Przygotowuje argumenty konstruktora, analizując kompozycje."""
        constructor_args = {}

        # Pobierz sygnaturę konstruktora
        try:
            class_obj = self.classes[class_name]['class_obj']
            init_sig = inspect.signature(class_obj.__init__)

            for param_name, param in init_sig.parameters.items():
                if param_name == 'self':
                    continue

                # Sprawdź czy w form_data jest bezpośrednia wartość dla tego parametru
                if param_name in form_data:
                    constructor_args[param_name] = form_data[param_name]
                else:
                    # Sprawdź czy to może być kompozycja - szukaj pól z prefiksem
                    # Dla Klasa2(aaaa_aaa, aaaa_dddd) szukaj pól zaczynających się od nazwy klasy
                    potential_prefix = f"{class_name.lower()}_"
                    matching_fields = {k: v for k, v in form_data.items()
                                       if k.startswith(potential_prefix)}

                    if matching_fields:
                        # Usuń prefiks i użyj jako argument
                        clean_param = param_name.replace(potential_prefix, "")
                        if f"{potential_prefix}{clean_param}" in form_data:
                            constructor_args[param_name] = form_data[f"{potential_prefix}{clean_param}"]

                    # Jeśli nadal nie znaleziono, spróbuj dopasować po typie parametru
                    if param_name not in constructor_args:
                        param_type_str = str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any"
                        param_type_name = param_type_str.split('.')[-1]

                        # Szukaj pól które mogą pasować do tego typu
                        for field_name, field_value in form_data.items():
                            if param_type_name.lower() in field_name.lower():
                                constructor_args[param_name] = field_value
                                break

                        # Ostatnia deska ratunku - użyj wartości domyślnej lub None
                        if param_name not in constructor_args:
                            if param.default != inspect.Parameter.empty:
                                constructor_args[param_name] = param.default
                            else:
                                # Spróbuj znaleźć wartość na podstawie nazwy parametru
                                for field_name, field_value in form_data.items():
                                    if param_name in field_name or field_name in param_name:
                                        constructor_args[param_name] = field_value
                                        break

        except Exception as e:
            print(f"Błąd podczas przygotowywania argumentów konstruktora: {e}")
            # Fallback - użyj form_data bezpośrednio
            constructor_args = form_data.copy()

        return constructor_args

    def _is_composition_field_type(self, field_type: str) -> bool:
        """Sprawdza czy typ pola to kompozycja."""
        return field_type in self.classes

    def _extract_composition_param_name(self, field_name: str, class_type: str) -> str:
        """Wyciąga nazwę parametru z nazwy pola kompozycji."""
        # Usuń prefiks nazwy klasy z nazwy pola
        class_prefix = class_type.lower() + "_"
        if field_name.startswith(class_prefix):
            return field_name[len(class_prefix):]
        return field_name

    def _find_composition_attribute_name(self, class_name: str, comp_type: str) -> str:
        """Znajduje nazwę atrybutu kompozycji w klasie."""
        if class_name not in self.classes:
            return None

        fields = self.classes[class_name].get('fields', [])
        for field in fields:
            if field['type'] == comp_type:
                return field['name']
        return None

    def _edit_selected_object(self):
        """Loads the selected object's data into the form for editing."""
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do edycji.")
            return

        item = selected_items[0]
        while item.parent(): item = item.parent() # Get top-level item
        object_name = item.text(0)

        if object_name not in self.objects or object_name not in self.object_data:
            QMessageBox.critical(self, "Błąd Wewnętrzny", f"Niespójność danych dla '{object_name}'.")
            return

        object_instance = self.objects[object_name]
        object_metadata = self.object_data[object_name]
        class_name = object_metadata['class']

        # --- Load data into form ---
        self.object_name_input.setText(object_name)

        # Set class combo and trigger form update
        class_index = self.object_class_combo.findText(class_name)
        if class_index >= 0:
            self.object_class_combo.blockSignals(True)
            self.object_class_combo.setCurrentIndex(class_index)
            self.object_class_combo.blockSignals(False)
            self._update_object_creation_form() # Rebuild form for the correct class
        else:
            QMessageBox.warning(self, "Ostrzeżenie", f"Klasa '{class_name}' obiektu nie znaleziona.")
            self._update_object_creation_form() # Update form based on current (possibly wrong) selection


        QApplication.processEvents() # Allow UI to update

        # --- Fill attribute widgets using current object state ---
        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not label_item or not field_item: continue
            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if not isinstance(label_widget, QLabel) or not field_widget: continue

            try: field_name = label_widget.text().split('(')[0].strip()
            except Exception: continue

            # Get current value directly from the object instance
            try: current_value = getattr(object_instance, field_name)
            except AttributeError:
                 current_value = object_metadata.get('attributes', {}).get(field_name, None) # Fallback
                 print(f"Info: Attr '{field_name}' not on instance, using metadata for edit.")
            except Exception as e:
                 current_value = f"<Błąd odczytu: {e}>"

            # Set widget value
            if isinstance(field_widget, QLineEdit):
                 if isinstance(current_value, (list, dict, set, tuple)):
                      try: field_widget.setText(repr(current_value)) # Show collections as literals
                      except Exception: field_widget.setText(str(current_value))
                 elif current_value is None: field_widget.clear()
                 else: field_widget.setText(str(current_value))
            elif isinstance(field_widget, QSpinBox):
                 try: field_widget.setValue(int(current_value) if current_value is not None else 0)
                 except (ValueError, TypeError): field_widget.setValue(0)
            elif isinstance(field_widget, QCheckBox):
                 field_widget.setChecked(bool(current_value))
            elif isinstance(field_widget, QComboBox): # Composition
                selected_obj_name = None
                if current_value is not None and isinstance(current_value, object):
                    # Find the name of the object referenced
                    for name, instance in self.objects.items():
                        if instance is current_value: # Check identity
                            selected_obj_name = name
                            break
                index = field_widget.findText(selected_obj_name) if selected_obj_name else -1
                field_widget.setCurrentIndex(index if index >= 0 else 0) # Select object or "(Brak)"


        self.raise_() # Bring window to front
        self.activateWindow()

        # ----- CORRECTED METHOD -----
    def _delete_selected_object(self):
        """Deletes the selected object after confirmation, checking references."""
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do usunięcia.")
            return

        # Find the top-level item (object name)
        item = selected_items[0]
        while item.parent():
            item = item.parent()
        object_name = item.text(0)

        if object_name not in self.objects:
            QMessageBox.warning(self, "Błąd", f"Nie znaleziono obiektu '{object_name}'.")
            return  # Already deleted?

        # Check for references TO this object
        referencing_info = []
        obj_to_delete_instance = self.objects[object_name]  # Get instance before loop

        for other_name, other_instance in self.objects.items():
            if other_name == object_name: continue  # Skip self-reference check

            try:
                other_class_name = other_instance.__class__.__name__
                if other_class_name in self.classes:  # Only check objects of known classes
                    fields_info = self._get_all_fields_recursive(other_class_name)
                    for field_info in fields_info:
                        field = field_info['field']
                        field_type_str = field['type']  # Get the type string (e.g., "Book", "Optional[Book]")

                        # --- Corrected Check: Determine if this field *could* hold a reference ---
                        can_hold_reference = False
                        # Get base part (e.g., 'Book', 'Optional', 'List') removing module prefixes potentially
                        base_type = field_type_str.split('.')[-1].split('[')[0]

                        if base_type in self.classes:
                            # Case 1: Direct type match (e.g., field type is "Book")
                            can_hold_reference = True
                        # Case 2: Optional or Union containing a known class
                        elif ('Optional' in field_type_str or ('Union' in field_type_str and \
                                                               (
                                                                       'None' in field_type_str or 'NoneType' in field_type_str))) and \
                                '[' in field_type_str:
                            # Check inside the brackets for a known class name
                            try:
                                # Extract content inside the last pair of brackets
                                content = field_type_str[field_type_str.rfind('[') + 1:field_type_str.rfind(']')]
                                parts = content.split(',')  # Split potential Union parts
                                # Check if any part (excluding None) is a known class after cleaning
                                can_hold_reference = any(
                                    part.strip().split('.')[-1].strip("'\" ") in self.classes
                                    for part in parts if part.strip().lower() not in ['none', 'nonetype']
                                )
                            except Exception:
                                # Error during parsing, assume false
                                can_hold_reference = False
                        # --- End Corrected Check ---

                        # --- If it can hold a reference, check the actual value ---
                        if can_hold_reference:
                            try:
                                ref_value = getattr(other_instance, field['name'])
                                # Check if the actual value is the object we intend to delete
                                if ref_value is obj_to_delete_instance:  # Use identity check (is)
                                    referencing_info.append(f"{other_name}.{field['name']}")
                            except AttributeError:
                                pass  # Attribute might not exist on the instance currently
                            except Exception as e_get:
                                print(
                                    f"Error getting attribute {other_name}.{field['name']} for ref check: {e_get}")

            except Exception as e_outer:
                print(f"Error inspecting object {other_name} for references: {e_outer}")  # Log outer loop error

        # --- Ask for confirmation ---
        message = f"Czy na pewno chcesz usunąć obiekt '{object_name}'?"
        if referencing_info:
            message += "\n\nUWAGA: Referencje do tego obiektu istnieją w:\n- "
            message += "\n- ".join(referencing_info)
            message += "\n\nUsunięcie spowoduje, że te referencje zostaną ustawione na None."

        reply = QMessageBox.warning(  # Use warning level due to potential broken references
            self, "Potwierdzenie Usunięcia", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No  # Default to No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # --- Perform deletion ---
            try:
                # 1. Set references to None in referencing objects
                for ref_str in referencing_info:
                    try:
                        ref_obj_name, ref_attr_name = ref_str.split('.', 1)
                        if ref_obj_name in self.objects:  # Check if referencing object still exists
                            print(f"Setting {ref_obj_name}.{ref_attr_name} to None (was {object_name})")
                            setattr(self.objects[ref_obj_name], ref_attr_name, None)
                            # Also update metadata for the referencing object
                            if ref_obj_name in self.object_data and 'attributes' in self.object_data[ref_obj_name]:
                                if ref_attr_name in self.object_data[ref_obj_name]['attributes']:
                                    self.object_data[ref_obj_name]['attributes'][ref_attr_name] = None
                    except Exception as e_set:
                        print(
                            f"Error setting reference to None in {ref_str}: {e_set}")  # Log error during setting None

                # 2. Delete the object and its metadata
                del self.objects[object_name]
                if object_name in self.object_data:
                    del self.object_data[object_name]

                # 3. Signal changes
                self.objects_changed.emit()
                QMessageBox.information(self, "Sukces", f"Obiekt '{object_name}' został usunięty.")

                # 4. Clear edit form if the deleted object was loaded
                if self.object_name_input.text() == object_name:
                    self.object_name_input.clear()
                    # Find index of deleted class or set to -1
                    class_name_deleted = self.object_data.get(object_name, {}).get(
                        'class')  # Get class before deleting data
                    if class_name_deleted:
                        index = self.object_class_combo.findText(class_name_deleted)
                        if index >= 0:
                            self.object_class_combo.setCurrentIndex(-1)  # Deselect class
                    else:
                        self.object_class_combo.setCurrentIndex(-1)
                    self._update_object_creation_form()  # Clear form fields


            except KeyError:
                QMessageBox.critical(self, "Błąd",
                                     f"Nie udało się usunąć obiektu '{object_name}' (KeyError - już usunięty?).")
            except Exception as e:
                QMessageBox.critical(self, "Błąd",
                                     f"Wystąpił nieoczekiwany błąd podczas usuwania '{object_name}': {e}")
    def _save_objects_to_mongodb(self):
        """Saves all current objects to MongoDB (requires PyMongoConverter)."""
        if not self.objects:
             QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
             return

        try:
            # --- Dynamic Import ---
            # Assume PyMongoConverter is in MongoDB/main.py relative to this script
            # You might need to adjust the import path based on your project structure
            try:
                from MongoDB.main import PyMongoConverter
            except ImportError:
                 # Try importing from current directory if MongoDB folder doesn't work
                 try:
                      from main import PyMongoConverter # If main.py is in the same dir
                 except ImportError:
                      QMessageBox.critical(self, "Błąd Importu",
                                          "Nie znaleziono klasy 'PyMongoConverter'.\n"
                                          "Upewnij się, że plik z konwerterem (np. MongoDB/main.py lub main.py) istnieje.")
                      return
            # Import pymongo separately to check for its existence too
            import pymongo

            # --- Connection Details (Hardcoded for example) ---
            connection_string = "mongodb://localhost:27017/"
            db_name = "object_generator_db"

            converter = None
            try:
                print(f"Connecting to MongoDB: {connection_string}, DB: {db_name}")
                converter = PyMongoConverter(connection_string=connection_string, db_name=db_name)
                converter.client.admin.command('ping') # Test connection
                print("MongoDB connection successful.")

                saved_count = 0
                errors = []
                # Pass self.objects for reference resolution during saving
                for obj_name, obj in self.objects.items():
                    print(f"Saving {obj_name} ({obj.__class__.__name__})...")
                    try:
                        # Save with object name as _id
                        converter.save_to_mongodb(obj)
                        saved_count += 1
                    except Exception as e:
                        error_msg = f"Failed saving '{obj_name}': {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)

                if not errors:
                    QMessageBox.information(self, "Sukces", f"Zapisano {saved_count} obiektów do MongoDB (Baza: {db_name}).")
                else:
                     QMessageBox.warning(self, "Błędy Zapisu",
                                         f"Zapisano {saved_count}/{len(self.objects)} obiektów.\n\nBłędy:\n" + "\n".join(errors))

            except pymongo.errors.ConnectionFailure as e:
                 QMessageBox.critical(self, "Błąd Połączenia MongoDB", f"Nie można połączyć z MongoDB.\n{e}")
            except Exception as e:
                 QMessageBox.critical(self, "Błąd Zapisu MongoDB", f"Wystąpił błąd: {str(e)}")
            finally:
                if converter: converter.close()

        except ImportError:
             QMessageBox.critical(self, "Brak Biblioteki", "Biblioteka 'pymongo' nie jest zainstalowana (`pip install pymongo`).")
        except Exception as e:
             QMessageBox.critical(self, "Błąd", f"Nieoczekiwany błąd: {e}")

    def _save_objects_to_cassandra(self):
        """Saves all current objects to Cassandra (requires PyCassandraConverter)."""
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
            return

        try:
            # --- Dynamic Import ---
            # Assume PyCassandraConverter is in Cassandra/main.py or main.py
            # Adjust the import path based on your project structure
            try:
                # Adjust path as needed (e.g., 'Cassandra.converter', 'utils.cassandra_converter')
                from Cassandra.main import PyCassandraConverter
            except ImportError:
                try:
                    # If main.py is in the same directory or package
                    from main import PyCassandraConverter
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'PyCassandraConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. Cassandra/main.py lub main.py) istnieje.")
                    return

            # Import Cassandra driver specifics for error handling
            from cassandra.cluster import NoHostAvailable

            # --- Connection Details (Keyspace provided) ---
            # Contact points might be hardcoded in PyCassandraConverter,
            # passed via config, or passed here if the constructor accepts them.
            keyspace = "object_db"  # As requested by the user

            converter = None
            try:
                print(f"Initializing Cassandra connection for keyspace: {keyspace}")
                # Instantiate the Cassandra converter as requested
                # Assumes PyCassandraConverter handles cluster connection internally
                converter = PyCassandraConverter(keyspace=keyspace)

                # Optional: Add a method to PyCassandraConverter to explicitly test
                # the connection if needed, otherwise assume connection happens
                # during instantiation or first use.
                # e.g., converter.test_connection()
                print("PyCassandraConverter initialized.")

                saved_count = 0
                errors = []
                # Iterate through objects to save
                for obj_name, obj in self.objects.items():
                    print(f"Saving {obj_name} ({obj.__class__.__name__}) to Cassandra...")
                    try:
                        # Save using the Cassandra specific method
                        converter.save_to_cassandra(obj)
                        saved_count += 1
                    except Exception as e:
                        # Catch potential errors during the save operation for a single object
                        error_msg = f"Failed saving '{obj_name}' to Cassandra: {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)

                # Report results
                if not errors:
                    QMessageBox.information(self, "Sukces",
                                            f"Zapisano {saved_count} obiektów do Cassandra (Keyspace: {keyspace}).")
                else:
                    QMessageBox.warning(self, "Błędy Zapisu",
                                        f"Zapisano {saved_count}/{len(self.objects)} obiektów do Cassandra.\n\nBłędy:\n" + "\n".join(
                                            errors))

            except NoHostAvailable as e:
                # Specific error for Cassandra connection failure
                QMessageBox.critical(self, "Błąd Połączenia Cassandra",
                                     f"Nie można połączyć z klastrem Cassandra dla keyspace '{keyspace}'.\nSprawdź ustawienia i dostępność bazy.\n{e}")
            except Exception as e:
                # Catch other potential errors (e.g., during converter initialization, general save errors)
                QMessageBox.critical(self, "Błąd Zapisu Cassandra", f"Wystąpił nieoczekiwany błąd: {str(e)}")
            finally:
                # Ensure the Cassandra connection is closed
                if converter:
                    try:
                        print("Closing Cassandra connection...")
                        converter.close()  # Assumes the converter has a close method
                        print("Cassandra connection closed.")
                    except Exception as e:
                        print(f"Error closing Cassandra connection: {e}")


        except ImportError:
            # Error if the cassandra-driver library is missing
            QMessageBox.critical(self, "Brak Biblioteki",
                                 "Biblioteka 'cassandra-driver' nie jest zainstalowana.\n"
                                 "Zainstaluj ją używając: pip install cassandra-driver")
        except Exception as e:
            # Catch any other unexpected errors (e.g., during dynamic import)
            QMessageBox.critical(self, "Błąd", f"Nieoczekiwany błąd: {e}")

    def _save_objects_to_neo4j(self):
        """Saves all current objects to Neo4j (requires Neo4jConverter), but only saves top-level objects and their connected objects."""
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
            return

        try:
            # Dynamic import of the Neo4jConverter class
            try:
                from Neo4j.main import Neo4jConverter
            except ImportError:
                try:
                    from main import Neo4jConverter  # Try local dir
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'Neo4jConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. Neo4j/main.py lub main.py) istnieje.")
                    return

            # --- Connection Details (adjust as needed) ---
            uri = "bolt://localhost:7687"
            user = "neo4j"
            password = "password"

            converter = None
            try:
                print(f"Connecting to Neo4j at {uri} as user '{user}'")
                converter = Neo4jConverter(uri=uri, user=user, password=password)

                # Find top-level objects (objects not referenced by other objects)
                top_level_objects = self._find_top_level_objects()

                if not top_level_objects:
                    QMessageBox.information(self, "Informacja", "Brak obiektów najwyższego poziomu do zapisania.")
                    return

                saved_count = 0
                errors = []

                for obj_name in top_level_objects:
                    obj = self.objects[obj_name]
                    print(f"Saving top-level object {obj_name} ({obj.__class__.__name__}) and its references...")
                    try:
                        converter.save(obj)
                        saved_count += 1
                    except Exception as e:
                        error_msg = f"Nie udało się zapisać '{obj_name}': {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)

                if not errors:
                    QMessageBox.information(self, "Sukces",
                                            f"Zapisano {saved_count} obiektów najwyższego poziomu do Neo4j.")
                else:
                    QMessageBox.warning(self, "Błędy Zapisu",
                                        f"Zapisano {saved_count}/{len(top_level_objects)} obiektów.\n\nBłędy:\n" + "\n".join(
                                            errors))

            except Exception as e:
                QMessageBox.critical(self, "Błąd Połączenia Neo4j", f"Nie można połączyć z Neo4j.\n{e}")
            finally:
                if converter:
                    converter.close()

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nieoczekiwany błąd: {e}")

    def _find_top_level_objects(self) -> List[str]:
        """Finds objects that are not referenced by other objects (top-level objects)."""
        referenced_objects = set()

        # First pass: find all objects that are referenced by other objects
        for obj_name, obj_instance in self.objects.items():
            class_name = obj_instance.__class__.__name__
            if class_name not in self.classes:
                continue  # Skip objects of unknown classes

            # Get all fields that could contain object references
            fields_info = self._get_all_fields_recursive(class_name)
            for field_info in fields_info:
                field = field_info['field']
                field_type = field['type']

                # Check if this field could hold an object reference
                if self._is_object_reference_type(field_type):
                    try:
                        referenced_obj = getattr(obj_instance, field['name'])
                        if referenced_obj is not None:
                            # Find the name of this referenced object
                            for ref_name, ref_instance in self.objects.items():
                                if ref_instance is referenced_obj:
                                    referenced_objects.add(ref_name)
                                    break
                    except AttributeError:
                        pass

        # Top-level objects are those not in referenced_objects
        top_level = [name for name in self.objects.keys() if name not in referenced_objects]
        return top_level

    def _is_object_reference_type(self, type_str: str) -> bool:
        """Determines if a type string represents an object reference type."""
        # Check if this is a direct class reference
        if type_str in self.classes:
            return True

        # Check for Optional[Class] or Union[Class, None]
        if '[' in type_str and ']' in type_str:
            try:
                content = type_str[type_str.find('[') + 1:type_str.rfind(']')]
                parts = [p.strip() for p in content.split(',')]
                for part in parts:
                    if part.lower() not in ['none', 'nonetype']:
                        # Check if part is a known class (remove any module prefix)
                        class_name = part.split('.')[-1].strip("'\" ")
                        if class_name in self.classes:
                            return True
            except Exception:
                pass

        return False

    def _get_object_attribute_safely(self, obj_instance, attr_name):
        """Bezpiecznie pobiera atrybut obiektu, obsługując kompozycje."""
        try:
            # Najpierw spróbuj standardowego getattr
            return getattr(obj_instance, attr_name)
        except AttributeError:
            # Jeśli nie ma atrybutu, sprawdź czy to może być kompozycja
            # Szukaj atrybutów które mogą zawierać pożądane dane
            for actual_attr_name in dir(obj_instance):
                if actual_attr_name.startswith('_'):
                    continue
                try:
                    actual_attr_value = getattr(obj_instance, actual_attr_name)
                    # Sprawdź czy to obiekt kompozycji który ma pożądany atrybut
                    if hasattr(actual_attr_value, attr_name.split('_')[-1]):
                        return getattr(actual_attr_value, attr_name.split('_')[-1])
                except:
                    continue

            # Jeśli nadal nie znaleziono, zwróć None
            return None

    def _update_object_tree(self):
        """Updates the tree view with the current state of objects."""
        self.object_tree.clear()
        sorted_object_names = sorted(self.objects.keys())

        for obj_name in sorted_object_names:
            obj_instance = self.objects.get(obj_name)
            obj_metadata = self.object_data.get(obj_name)
            if obj_instance is None or obj_metadata is None:
                continue  # Skip inconsistent data

            obj_item = QTreeWidgetItem([obj_name])
            font = obj_item.font(0)
            font.setBold(True)
            obj_item.setFont(0, font)
            self.object_tree.addTopLevelItem(obj_item)

            class_name = obj_instance.__class__.__name__
            class_item = QTreeWidgetItem(["Klasa", class_name])
            obj_item.addChild(class_item)

            attributes_item = QTreeWidgetItem(["Atrybuty"])
            obj_item.addChild(attributes_item)

            try:
                all_fields_info = self._get_all_fields_recursive(class_name)
                field_names = sorted([info['field']['name'] for info in all_fields_info])

                if not field_names:
                    attributes_item.addChild(QTreeWidgetItem(["(Brak pól)", ""]))

                for attr_name in field_names:
                    attr_value_str = "<Błąd odczytu>"  # Initialize default value
                    try:
                        attr_value = self._get_object_attribute_safely(obj_instance, attr_name)
                        
                        if attr_value is None:
                            attr_value_str = "None"
                        elif isinstance(attr_value, str):
                            attr_value_str = f'"{attr_value}"'
                        elif isinstance(attr_value, (int, float, bool)):
                            attr_value_str = str(attr_value)
                        elif isinstance(attr_value, list):
                            if attr_value:  # Check if list is not empty
                                # Check if it's a list of known objects
                                is_list_of_known_objects = all(
                                    any(o is item for _, o in self.objects.items()) 
                                    for item in attr_value
                                )
                                if is_list_of_known_objects:
                                    item_names = []
                                    for item in attr_value:
                                        found_name = None
                                        for ref_name, ref_instance in self.objects.items():
                                            if ref_instance is item:
                                                found_name = ref_name
                                                break
                                        item_names.append(f"-> {found_name}" if found_name else f"<{item.__class__.__name__}>")
                                    attr_value_str = f"[{', '.join(item_names)}]"
                                else:  # Generic list
                                    repr_val = repr(attr_value)
                                    attr_value_str = repr_val[:80] + ('...' if len(repr_val) > 80 else '')
                            else:  # Empty list
                                attr_value_str = "[]"
                        elif isinstance(attr_value, dict):
                            attr_value_str = str({k: str(v)[:20] + ('...' if len(str(v)) > 20 else '') 
                                                for k, v in attr_value.items()})
                        elif any(attr_value is obj for obj in self.objects.values()):
                            # Handle single object reference
                            ref_name = next((name for name, obj in self.objects.items() 
                                        if obj is attr_value), None)
                            attr_value_str = f"-> {ref_name}" if ref_name else f"<{attr_value.__class__.__name__}>"
                        else:
                            attr_value_str = str(attr_value)[:80] + ('...' if len(str(attr_value)) > 80 else '')
                    except AttributeError:
                        attr_value_str = "<Atrybut nie istnieje>"
                    except Exception as e:
                        attr_value_str = f"<Błąd odczytu: {e}>"

                    attr_item = QTreeWidgetItem([attr_name, attr_value_str])
                    attributes_item.addChild(attr_item)

            except Exception as e:
                attributes_item.addChild(QTreeWidgetItem([f"<Błąd przetwarzania: {e}>", ""]))

            obj_item.setExpanded(True)  # Expand object node
            attributes_item.setExpanded(True)  # Expand attributes node

    def _update_composition_combos(self):
        """Updates composition QComboBoxes in the creation form."""
        # print("Updating composition combos in form...") # Debug
        for i in range(self.object_fields_layout.rowCount()):
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not field_item: continue
            field_widget = field_item.widget()

            if isinstance(field_widget, QComboBox): # Found a combo - check if it's for composition
                label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                expected_base_type = None
                if label_item and isinstance(label_item.widget(), QLabel):
                    label_text = label_item.widget().text()
                    try: # Extract expected base type from label (e.g., 'Book' from 'book_obj (Optional[Book])')
                        type_part = label_text.split('(')[1].split(')')[0]
                        base_type_str = type_part.split('[')[0].strip() # e.g. Optional, List, Book
                        if base_type_str in self.classes: expected_base_type = base_type_str
                        elif '[' in type_part: # Check inside generics
                             content = type_part[type_part.find('[')+1:type_part.rfind(']')]
                             parts = [p.strip() for p in content.split(',')]
                             for part in parts:
                                  if part.lower() != 'none' and part.lower() != 'nonetype':
                                       potential_name = part.split('.')[-1].strip("'\" ")
                                       if potential_name in self.classes:
                                            expected_base_type = potential_name; break
                    except Exception: pass # Ignore label parsing errors

                if not expected_base_type: continue # Skip if not a known class composition combo

                # Repopulate this combo
                field_widget.blockSignals(True)
                current_selection_name = field_widget.currentText()
                field_widget.clear()
                field_widget.addItem("(Brak)")
                items_added = 0
                for obj_name, obj_instance in sorted(self.objects.items()):
                    if obj_instance.__class__.__name__ == expected_base_type:
                        field_widget.addItem(obj_name)
                        items_added += 1

                index_to_select = field_widget.findText(current_selection_name)
                field_widget.setCurrentIndex(index_to_select if index_to_select >= 0 else 0)
                field_widget.blockSignals(False)
                # print(f"Updated combo for {expected_base_type}: {items_added} items. Selected: {field_widget.currentText()}")

    def _show_connect_objects_dialog(self):
        """Shows the dialog for connecting objects."""
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do połączenia.")
            return

        dialog = ConnectObjectsDialog(self.objects, self.classes, self)
        if dialog.exec(): # True if OK clicked
            connection_details = dialog.get_connection_details()
            if connection_details:
                target_name, attr_name, source_name = connection_details
                self._perform_object_connection(target_name, attr_name, source_name)
            # else: QMessageBox.warning(self,"Anulowano","Nie wybrano poprawnie obiektów/atrybutu.")

# In class ObjectGeneratorApp:
    # ...
    def _perform_object_connection(self, target_obj_name: str, attribute_name: str, source_obj_data: Any): # Any is str or List[str]
        """Sets the target object's attribute(s)."""
        try:
            target_obj = self.objects[target_obj_name]
            
            connection_message_suffix = ""

            if isinstance(source_obj_data, list): # Target attribute is a list of objects
                # Get the list attribute from the target object, or initialize if not present/not a list
                target_list_attr = getattr(target_obj, attribute_name, None)
                if not isinstance(target_list_attr, list):
                    print(f"Info: Attribute '{attribute_name}' on '{target_obj_name}' was not a list. Initializing.")
                    target_list_attr = []
                    setattr(target_obj, attribute_name, target_list_attr)
                
                target_list_attr.clear() # Replace current content
                
                actual_connected_names = []
                for src_name in source_obj_data: # source_obj_data is List[str]
                    source_obj_instance = self.objects.get(src_name)
                    if source_obj_instance:
                        target_list_attr.append(source_obj_instance)
                        actual_connected_names.append(src_name)
                    else:
                        print(f"Warning: Source object '{src_name}' not found during list connection.")
                
                # For metadata, store the list of actual objects (references)
                if target_obj_name in self.object_data and 'attributes' in self.object_data[target_obj_name]:
                    self.object_data[target_obj_name]['attributes'][attribute_name] = list(target_list_attr) # Store a copy

                connection_message_suffix = f"-> [{', '.join(actual_connected_names)}]"
                print(f"Connecting list: {target_obj_name}.{attribute_name} set to {len(actual_connected_names)} object(s).")

            else: # Target attribute is a single object (source_obj_data is str)
                source_obj_instance = self.objects.get(source_obj_data) # source_obj_data is single name or "(Brak)"
                
                setattr(target_obj, attribute_name, source_obj_instance)

                # Update metadata
                if target_obj_name in self.object_data and 'attributes' in self.object_data[target_obj_name]:
                    self.object_data[target_obj_name]['attributes'][attribute_name] = source_obj_instance
                
                connection_message_suffix = f"-> {source_obj_data if source_obj_instance else 'None'}"
                print(f"Connecting single: {target_obj_name}.{attribute_name} = {source_obj_data if source_obj_instance else 'None'}")

            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces", f"Połączono: {target_obj_name}.{attribute_name} {connection_message_suffix}.")

        except KeyError as e:
            QMessageBox.critical(self, "Błąd", f"Nie znaleziono obiektu: {e}")
        except Exception as e: # Catch broader exceptions like AttributeError
            QMessageBox.critical(self, "Błąd Połączenia", f"Nie udało się ustawić atrybutu.\nBłąd: {e}")
            import traceback
            traceback.print_exc()


# --- Application Entry Point ---
if __name__ == "__main__":
    CLASSES_MODULE_NAME = "wygenerowany_kod" # Name of your classes file (without .py)
    try:
        # Attempt to import the module with class definitions
        classes_module = importlib.import_module(CLASSES_MODULE_NAME)
        print(f"Successfully imported module: {CLASSES_MODULE_NAME}")
    except ImportError:
        # Create a dummy module if import fails
        msg = (f"BŁĄD: Nie można zaimportować modułu '{CLASSES_MODULE_NAME}'.\n"
               f"Upewnij się, że plik '{CLASSES_MODULE_NAME}.py' istnieje w tym samym folderze.\n"
               "Aplikacja uruchomi się bez załadowanych klas.")
        print(msg)
        # Need a temporary app instance just to show the message box
        _temp_app = QApplication.instance() # Get existing instance if any
        if _temp_app is None: # Create one if none exists
             _temp_app = QApplication(sys.argv)
        QMessageBox.critical(None, "Błąd Importu Modułu", msg)
        # Create a dummy module object
        from types import ModuleType
        classes_module = ModuleType(CLASSES_MODULE_NAME)
        # sys.exit(1) # Option to exit if module is crucial

    app = QApplication.instance() # Get existing instance
    if app is None: # Create if does not exist
        app = QApplication(sys.argv)

    # Create and show the main window
    window = ObjectGeneratorApp(classes_module)
    window.show()

    # Start the application event loop
    sys.exit(app.exec())