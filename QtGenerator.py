import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,QComboBox, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QFormLayout, QScrollArea,
    QSpinBox, QCheckBox, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import  pyqtSignal, QLocale
from PyQt6.QtGui import QDoubleValidator
from typing import Dict, List, Optional, Any, Tuple
import random
import string
import importlib
import inspect
import ast

# --- Type Definitions (Optional but good practice) ---
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any]
ObjectsDict = Dict[str, Any] # Stores actual Python objects


# --- Dialog for Connecting Objects ---
class ConnectObjectsDialog(QDialog):
    def __init__(self, objects_dict: ObjectsDict, classes_dict: ClassesDict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Połącz Obiekty")
        self.objects = objects_dict
        self.classes = classes_dict
        self.target_object = None
        self.target_attribute = None
        self.source_object = None

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # 1. Select Target Object
        self.target_object_combo = QComboBox()
        self.target_object_combo.addItem("-- Wybierz obiekt docelowy --")
        self.target_object_combo.addItems(sorted(self.objects.keys()))
        self.target_object_combo.currentIndexChanged.connect(self._update_target_attributes)
        form_layout.addRow("Obiekt docelowy:", self.target_object_combo)

        # 2. Select Target Attribute (filtered for composition)
        self.target_attribute_combo = QComboBox()
        self.target_attribute_combo.setEnabled(False) # Enable when target is selected
        self.target_attribute_combo.currentIndexChanged.connect(self._update_source_objects)
        form_layout.addRow("Atrybut docelowy:", self.target_attribute_combo)

        # 3. Select Source Object (filtered by attribute type)
        self.source_object_combo = QComboBox()
        self.source_object_combo.setEnabled(False) # Enable when attribute is selected
        form_layout.addRow("Obiekt źródłowy:", self.source_object_combo)

        layout.addLayout(form_layout)

        # OK and Cancel buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        """ Helper to get fields recursively (copied for dialog use)."""
        # This should ideally use the main app's method if possible,
        # but copying it here makes the dialog self-contained regarding this logic.
        if class_name not in self.classes:
            return []
        if visited is None: visited = set()
        if class_name in visited: return []
        visited.add(class_name)
        fields_map = {}
        parent_class = self.classes[class_name].get('inherits')
        if parent_class and parent_class in self.classes: # Check parent exists
            parent_fields = self._get_all_fields_recursive(parent_class, visited.copy())
            for field_info in parent_fields:
                fields_map[field_info['field']['name']] = field_info
        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source_class': class_name}
        return list(fields_map.values())

    # --- THIS METHOD CONTAINS THE FIX ---
    def _update_target_attributes(self):
        """Update the attribute combo based on the selected target object."""
        self.target_attribute_combo.clear()
        self.target_attribute_combo.setEnabled(False)
        self._update_source_objects() # Clear source objects too

        target_obj_name = self.target_object_combo.currentText()
        if not target_obj_name or target_obj_name.startswith("--"):
            return

        try:
            # Get class name from the actual object instance
            target_obj_instance = self.objects.get(target_obj_name)
            if not target_obj_instance:
                 self.target_attribute_combo.addItem("-- Obiekt docelowy nie istnieje --")
                 return

            target_class_name = target_obj_instance.__class__.__name__
            if target_class_name not in self.classes:
                 self.target_attribute_combo.addItem("-- Klasa obiektu nieznana --")
                 return

            compatible_attributes = []
            # Use the main app's recursive field getter if possible, or the dialog's copy
            # Assuming the dialog has access or uses its own copy:
            all_fields = self._get_all_fields_recursive(target_class_name)

            # --- Start of Parsing Logic ---
            for field_info in all_fields:
                field = field_info['field']
                field_type_str = field['type'] # e.g., "Optional[Book]", "str", "int", "Book"

                base_class_name = None
                # Try to extract base class name from complex types like Optional[X] or Union[X, None]
                if '[' in field_type_str and ']' in field_type_str:
                    try:
                        # Extract content within brackets: e.g., 'Book' from Optional['Book']
                        # Or 'wygenerowany_kod.Book, NoneType' from Union[...]
                        content = field_type_str[field_type_str.find('[')+1:field_type_str.rfind(']')]
                        # Split if it's a Union
                        parts = [p.strip() for p in content.split(',')]
                        for part in parts:
                            # Ignore None/NoneType
                            if part.lower() != 'none' and part.lower() != 'nonetype':
                                # Handle qualified names like 'wygenerowany_kod.Book' -> 'Book'
                                potential_name = part.split('.')[-1].strip("'\" ") # Remove quotes/spaces
                                # Check if this extracted name is one of our known classes
                                if potential_name in self.classes:
                                    base_class_name = potential_name
                                    break # Found the relevant class name
                    except Exception as e:
                        # Parsing failed, log it maybe?
                        print(f"Debug: Failed to parse type string '{field_type_str}': {e}")
                        base_class_name = None
                elif field_type_str in self.classes:
                    # It's a direct match for a simple type like "Book"
                    base_class_name = field_type_str

                # If we successfully identified a base class name known to the app, add the attribute
                if base_class_name:
                    compatible_attributes.append(field['name'])
            # --- End of Parsing Logic ---

            if compatible_attributes:
                self.target_attribute_combo.addItem("-- Wybierz atrybut --")
                self.target_attribute_combo.addItems(sorted(compatible_attributes))
                self.target_attribute_combo.setEnabled(True)
            else:
                # This is the message you were seeing when logic failed
                self.target_attribute_combo.addItem("-- Brak atrybutów obiektowych --")

        except KeyError:
             self.target_attribute_combo.addItem("-- Błąd pobierania klasy obiektu --")
        except Exception as e:
             self.target_attribute_combo.addItem(f"-- Błąd: {e} --")
             print(f"Error in _update_target_attributes: {e}") # Print error for debugging


    def _update_source_objects(self):
        """Update the source object combo based on the selected target attribute type."""
        self.source_object_combo.clear()
        self.source_object_combo.setEnabled(False)

        target_obj_name = self.target_object_combo.currentText()
        attribute_name = self.target_attribute_combo.currentText()

        if not target_obj_name or target_obj_name.startswith("--") or \
           not attribute_name or attribute_name.startswith("--"):
            return

        try:
            # Find the expected type for the selected attribute
            target_obj_instance = self.objects.get(target_obj_name)
            if not target_obj_instance: return # Target object disappeared?
            target_class_name = target_obj_instance.__class__.__name__

            expected_base_type = None
            all_fields = self._get_all_fields_recursive(target_class_name)
            for field_info in all_fields:
                if field_info['field']['name'] == attribute_name:
                    field_type_str = field_info['field']['type']
                    # --- Reuse parsing logic to find the expected base type ---
                    if '[' in field_type_str and ']' in field_type_str:
                         try:
                             content = field_type_str[field_type_str.find('[')+1:field_type_str.rfind(']')]
                             parts = [p.strip() for p in content.split(',')]
                             for part in parts:
                                  if part.lower() != 'none' and part.lower() != 'nonetype':
                                       potential_name = part.split('.')[-1].strip("'\" ")
                                       if potential_name in self.classes:
                                            expected_base_type = potential_name
                                            break
                         except Exception: pass # Ignore parsing error here
                    elif field_type_str in self.classes:
                         expected_base_type = field_type_str
                    # --- End reuse parsing ---
                    break # Found the attribute, stop searching

            if not expected_base_type:
                self.source_object_combo.addItem("-- Nieznany typ atrybutu --")
                return

            # Find existing objects of the expected base type (excluding the target itself)
            compatible_sources = []
            for obj_name, obj_instance in self.objects.items():
                 # Check class name directly from the instance
                 if obj_instance.__class__.__name__ == expected_base_type and obj_name != target_obj_name:
                    compatible_sources.append(obj_name)

            if compatible_sources:
                self.source_object_combo.addItem("-- Wybierz obiekt źródłowy --")
                self.source_object_combo.addItems(sorted(compatible_sources))
                self.source_object_combo.setEnabled(True)
            else:
                self.source_object_combo.addItem(f"-- Brak obiektów typu {expected_base_type} --")

        except KeyError:
             self.source_object_combo.addItem("-- Błąd pobierania danych --")
        except Exception as e:
             self.source_object_combo.addItem(f"-- Błąd: {e} --")
             print(f"Error in _update_source_objects: {e}")


    def get_connection_details(self) -> Optional[Tuple[str, str, str]]:
        """Returns the selected target object name, attribute name, and source object name."""
        target_obj_name = self.target_object_combo.currentText()
        attribute_name = self.target_attribute_combo.currentText()
        source_obj_name = self.source_object_combo.currentText()

        # Check if valid selections were made (not the placeholder text)
        if target_obj_name.startswith("--") or \
           attribute_name.startswith("--") or \
           source_obj_name.startswith("--"):
            return None # Invalid selection

        return target_obj_name, attribute_name, source_obj_name


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
            # Ensure it's a class defined directly in the target module
            if inspect.isclass(obj) and getattr(obj, '__module__', None) == module_name:
                parent = None
                # Check bases carefully
                try:
                    for base in obj.__bases__:
                        # Ensure base is also from the same module and not 'object'
                        if getattr(base, '__module__', None) == module_name and base is not object:
                             # Check if base class name exists as a key in potential classes from this module
                             base_name = base.__name__
                             # We might not have analyzed the base yet, just store the name
                             parent = base_name
                             break # Take the first valid parent found
                except AttributeError: # Handle classes without __bases__? Unlikely for user classes
                     pass

                fields = []
                try:
                    # Prefer __init__ signature
                    init_sig = inspect.signature(obj.__init__)
                    for param_name, param in init_sig.parameters.items():
                        if param_name == 'self': continue

                        param_type_str = "Any" # Default if unknown
                        annotation = param.annotation

                        if annotation != inspect.Parameter.empty:
                             if isinstance(annotation, str): # Handle forward references ('Book')
                                  param_type_str = annotation
                             elif hasattr(annotation, '__name__'): # Standard types (int, str, Book)
                                  param_type_str = annotation.__name__
                             elif hasattr(annotation, '__origin__'): # Generics (Optional, Union, List, Dict)
                                  origin = annotation.__origin__
                                  origin_name = getattr(origin, '__name__', str(origin))
                                  args = getattr(annotation, '__args__', [])
                                  arg_names = []
                                  for arg in args:
                                       if isinstance(arg, type(None)): arg_names.append('NoneType')
                                       elif hasattr(arg, '__name__'): arg_names.append(arg.__name__)
                                       elif isinstance(arg, str): arg_names.append(arg) # Forward ref within generic
                                       else: arg_names.append(str(arg))
                                  param_type_str = f"{origin_name}[{', '.join(arg_names)}]"
                             else: # Fallback for complex annotations
                                  param_type_str = str(annotation).replace(f"{module_name}.", "") # Clean up module name

                        elif param.default != inspect.Parameter.empty and param.default is not None:
                             # Infer type from default value if no annotation
                             param_type_str = type(param.default).__name__

                        fields.append({"name": param_name, "type": param_type_str})

                except (ValueError, TypeError, AttributeError): # Handle missing __init__ or other issues
                     # Fallback: check class annotations if __init__ fails
                    try:
                        annotations = inspect.get_annotations(obj, eval_str=True) # eval_str=True for forward refs
                        existing_field_names = {f['name'] for f in fields}
                        for attr_name, attr_type in annotations.items():
                             if not attr_name.startswith('_') and attr_name not in existing_field_names:
                                 type_name = "Any"
                                 if hasattr(attr_type, '__name__'): type_name = attr_type.__name__
                                 elif hasattr(attr_type, '__origin__'): # Generics in annotations
                                     origin = attr_type.__origin__
                                     origin_name = getattr(origin, '__name__', str(origin))
                                     args = getattr(attr_type, '__args__', [])
                                     arg_names = []
                                     for arg in args:
                                          if isinstance(arg, type(None)): arg_names.append('NoneType')
                                          elif hasattr(arg, '__name__'): arg_names.append(arg.__name__)
                                          else: arg_names.append(str(arg))
                                     type_name = f"{origin_name}[{', '.join(arg_names)}]"
                                 else: type_name = str(attr_type).replace(f"{module_name}.", "")

                                 fields.append({"name": attr_name, "type": type_name})
                    except Exception as e_annot:
                         print(f"Debug: Could not process annotations for {name}: {e_annot}")


                classes[name] = {
                    "fields": fields,
                    "inherits": parent,
                    "class_obj": obj
                }
                # print(f"Analyzed class: {name}, Fields: {fields}, Inherits: {parent}") # Debug print

        return classes

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
        # Clear previous widgets safely
        self._clear_layout(self.object_fields_layout)

        selected_class = self.object_class_combo.currentText()
        if not selected_class or selected_class not in self.classes:
            # Add a placeholder if the class isn't found or isn't selected
            if selected_class: # Only show if a specific invalid class was selected
                 self.object_fields_layout.addRow(QLabel(f"Klasa '{selected_class}' nieznana."))
            return

        # Get all fields (own and inherited)
        all_fields = self._get_all_fields_recursive(selected_class)

        if not all_fields:
            self.object_fields_layout.addRow(QLabel("Klasa nie ma definiowanych atrybutów do wypełnienia."))
            return

        # Sort fields by name
        all_fields.sort(key=lambda x: x['field']['name'])

        for field_info in all_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type'] # e.g., "int", "str", "Optional[Book]", "List[str]"

            # Determine the base type for widget selection and combo population
            base_type = field_type
            is_optional = False
            if '[' in field_type and ']' in field_type:
                 # Handle generics like Optional[X], List[X], Union[X, None]
                 try:
                     origin_part = field_type[:field_type.find('[')]
                     content_part = field_type[field_type.find('[')+1:field_type.rfind(']')]
                     args = [a.strip() for a in content_part.split(',')]

                     if origin_part in ['Optional', 'Union']:
                          # Find the non-None type in Optional/Union
                          non_none_args = [a for a in args if a.lower() != 'none' and a.lower() != 'nonetype']
                          if len(non_none_args) == 1:
                               base_type = non_none_args[0].split('.')[-1] # Use base name like 'Book'
                          is_optional = True # Mark as optional
                     elif origin_part in ['List', 'list', 'Dict', 'dict', 'Set', 'set', 'Tuple', 'tuple']:
                          base_type = origin_part # Base type is the collection itself
                     # else keep original field_type as base_type for unknown generics
                 except Exception:
                      pass # Keep original field_type if parsing fails


            label = QLabel(f"{field_name} ({field_type})") # Show full type info in label
            input_widget: Optional[QWidget] = None # Initialize widget variable

            # --- Create appropriate input widget based on the *base* field type ---
            if base_type == "int":
                input_widget = QSpinBox()
                input_widget.setRange(-2147483647, 2147483647) # Max 32-bit signed int
            elif base_type == "float":
                 input_widget = QLineEdit()
                 input_widget.setPlaceholderText("Wprowadź liczbę zmiennoprzecinkową")
                 # Add a validator for float input
                 validator = QDoubleValidator()
                 validator.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)) # Use '.' decimal separator
                 input_widget.setValidator(validator)
            elif base_type == "bool":
                input_widget = QCheckBox()
            elif base_type == "str":
                input_widget = QLineEdit()
            # Handle common collections shown as LineEdit for literal input
            elif base_type in ["list", "List", "dict", "Dict", "set", "Set", "tuple", "Tuple"]:
                input_widget = QLineEdit()
                input_widget.setPlaceholderText(f"Wpisz jako Python literal (np. [1,'a'])")
                input_widget.setToolTip(f"Oczekiwany typ: {field_type}")
            # Handle composition: base_type is a known class name
            elif base_type in self.classes:
                input_widget = QComboBox()
                input_widget.addItem("(Brak)") # Default/None option
                # Add existing objects of this type
                for obj_name, obj_instance in self.objects.items():
                    # Use actual object's class name for matching
                    if obj_instance.__class__.__name__ == base_type:
                        input_widget.addItem(obj_name)
            else:  # Unknown or complex type not handled above
                 input_widget = QLineEdit()
                 input_widget.setPlaceholderText(f"(Typ: {field_type})")
                 input_widget.setToolTip(f"Wprowadź wartość jako string lub Python literal dla typu: {field_type}")


            if input_widget is not None:
                 self.object_fields_layout.addRow(label, input_widget)
            else:
                 # Fallback label if widget creation failed (should not happen with current logic)
                 self.object_fields_layout.addRow(label, QLabel(f"Nieobsługiwany typ widgetu: {field_type}"))

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
            if not label_item or not field_item: continue
            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if not isinstance(label_widget, QLabel) or not field_widget: continue

            label_text = label_widget.text()
            try:
                 field_name = label_text.split('(')[0].strip()
                 field_type = label_text.split('(')[1][:-1].strip() # Type from label
                 base_type = field_type.split('[')[0] # Base type for logic
            except Exception: continue # Skip if label format wrong

            # Generate random value based on widget type / base type
            if isinstance(field_widget, QLineEdit):
                if base_type == "str": field_widget.setText(''.join(random.choices(string.ascii_letters + ' ', k=10)))
                elif base_type == "int": field_widget.setText(str(random.randint(0, 100)))
                elif base_type == "float": field_widget.setText(f"{random.uniform(0, 100):.2f}")
                elif base_type in ["list", "List"]: field_widget.setText(f"['{random.choice(['a','b','c'])}', {random.randint(1,5)}]")
                elif base_type in ["dict", "Dict"]: field_widget.setText(f"{{'key': {random.randint(1,10)}}}")
                else: field_widget.setText("random_val")
            elif isinstance(field_widget, QSpinBox): field_widget.setValue(random.randint(field_widget.minimum(), min(field_widget.maximum(), 100)))
            elif isinstance(field_widget, QCheckBox): field_widget.setChecked(random.choice([True, False]))
            elif isinstance(field_widget, QComboBox):  # Composition
                if field_widget.count() > 1: # Has options other than "(Brak)"
                    field_widget.setCurrentIndex(random.randint(1, field_widget.count() - 1))
                else: field_widget.setCurrentIndex(0)

    def _create_predefined_objects(self):
        """Creates predefined Book and Library objects if classes exist."""
        # This is kept simple, assuming specific fields ('pages', 'book_obj', 'city')
        created_objects = []
        try:
            book1, book2 = None, None # Initialize
            if 'Book' in self.classes and any(f['field']['name']=='pages' for f in self._get_all_fields_recursive('Book')):
                book_class = self.classes['Book']['class_obj']
                book1 = book_class(pages=200)
                self.objects['book1'] = book1
                self.object_data['book1'] = {'class': 'Book', 'attributes': {'pages': 200}}
                created_objects.append('book1')

                book2 = book_class(pages=350)
                self.objects['book2'] = book2
                self.object_data['book2'] = {'class': 'Book', 'attributes': {'pages': 350}}
                created_objects.append('book2')

            if 'Library' in self.classes and book1 and book2 and \
               any(f['field']['name']=='book_obj' for f in self._get_all_fields_recursive('Library')) and \
               any(f['field']['name']=='city' for f in self._get_all_fields_recursive('Library')):
                library_class = self.classes['Library']['class_obj']

                library1 = library_class(book_obj=book1, city="Warsaw")
                self.objects['library1'] = library1
                self.object_data['library1'] = {'class': 'Library', 'attributes': {'book_obj': book1, 'city': "Warsaw"}}
                created_objects.append('library1')

                library2 = library_class(book_obj=book2, city="Krakow")
                self.objects['library2'] = library2
                self.object_data['library2'] = {'class': 'Library', 'attributes': {'book_obj': book2, 'city': "Krakow"}}
                created_objects.append('library2')

            if created_objects:
                self.objects_changed.emit()
                QMessageBox.information(self, "Sukces", f"Utworzono przykładowe obiekty: {', '.join(created_objects)}")
            else:
                 QMessageBox.warning(self, "Informacja", "Nie utworzono żadnych przykładowych obiektów (brakujące klasy 'Book'/'Library' lub wymagane pola).")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć przykładowych obiektów: {str(e)}")

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
        if not object_name.isidentifier() or object_name in ['None', 'True', 'False']: # Basic check
             QMessageBox.warning(self, "Błąd", f"Nazwa obiektu '{object_name}' jest nieprawidłowa.")
             return

        is_update = object_name in self.objects
        target_class_obj = self.classes[class_name]['class_obj']

        # Warn if updating an object but the class selection changed
        if is_update and not isinstance(self.objects[object_name], target_class_obj):
              reply = QMessageBox.question(self, "Zmiana Typu Obiektu",
                                         f"Obiekt '{object_name}' jest typu '{self.objects[object_name].__class__.__name__}', "
                                         f"a wybrano klasę '{class_name}'.\n"
                                         f"Kontynuacja spowoduje próbę aktualizacji atrybutów nowej klasy.\n"
                                         f"Czy chcesz kontynuować?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
              if reply == QMessageBox.StandardButton.No: return

        attributes = {}
        conversion_errors = []
        valid_field_names_for_class = {f_info['field']['name'] for f_info in self._get_all_fields_recursive(class_name)}

        # Collect and validate attributes from form
        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not label_item or not field_item: continue
            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if not isinstance(label_widget, QLabel) or not field_widget: continue

            try: field_name = label_widget.text().split('(')[0].strip()
            except Exception: continue # Skip if label bad format

            # Only process fields relevant to the currently selected class
            if field_name not in valid_field_names_for_class:
                 continue

            value: Any = None
            try:
                if isinstance(field_widget, QLineEdit):
                    text_value = field_widget.text()
                    # Attempt smart conversion based on expected type (from label for simplicity)
                    expected_type_str = label_widget.text().split('(')[1][:-1].strip()
                    base_expected_type = expected_type_str.split('[')[0]

                    if not text_value: # Handle empty input based on type (allow None if Optional?)
                        is_optional = 'Optional' in expected_type_str or 'Union' in expected_type_str and ('None' in expected_type_str or 'NoneType' in expected_type_str)
                        if is_optional: value = None
                        elif base_expected_type == "int": value = 0
                        elif base_expected_type == "float": value = 0.0
                        elif base_expected_type == "bool": value = False
                        elif base_expected_type in ["list", "List"]: value = []
                        elif base_expected_type in ["dict", "Dict"]: value = {}
                        elif base_expected_type == "str": value = ""
                        else: value = None # Default None for other empty types
                    else:
                        # Attempt conversion
                        if base_expected_type == "int": value = int(text_value)
                        elif base_expected_type == "float": value = float(text_value)
                        elif base_expected_type == "bool":
                             lower_val = text_value.lower()
                             if lower_val in ['true', '1', 'yes', 't']: value = True
                             elif lower_val in ['false', '0', 'no', 'f']: value = False
                             else: raise ValueError("Oczekiwano wartości logicznej")
                        elif base_expected_type in ["list", "List", "dict", "Dict", "set", "Set", "tuple", "Tuple"]:
                            try: value = ast.literal_eval(text_value) # Use literal_eval for safety
                            except (ValueError, SyntaxError) as e: raise ValueError(f"Nieprawidłowy format dla {base_expected_type}: {e}")
                        elif base_expected_type == "str": value = text_value
                        else: value = text_value # Treat unknown types as strings

                elif isinstance(field_widget, QSpinBox): value = field_widget.value()
                elif isinstance(field_widget, QCheckBox): value = field_widget.isChecked()
                elif isinstance(field_widget, QComboBox): # Composition
                    selected_text = field_widget.currentText()
                    value = None if selected_text == "(Brak)" else self.objects.get(selected_text)
                    if selected_text != "(Brak)" and value is None:
                         raise ValueError(f"Wybrany obiekt '{selected_text}' nie istnieje.")

                attributes[field_name] = value

            except (ValueError, TypeError) as e:
                conversion_errors.append(f"Pole '{field_name}': {e}")

        if conversion_errors:
            QMessageBox.warning(self, "Błąd danych wejściowych", "Popraw błędy:\n\n" + "\n".join(conversion_errors))
            return

        # Create or update the object
        try:
            if is_update: # Update existing object
                obj = self.objects[object_name]
                print(f"Updating '{object_name}' with: {attributes}") # Debug
                for attr_name, attr_value in attributes.items():
                    setattr(obj, attr_name, attr_value) # Direct attribute setting
                # Update metadata (store the values just set)
                self.object_data[object_name]['attributes'].update(attributes)
                self.object_data[object_name]['class'] = class_name # Update class in metadata too
            else: # Create new object
                 print(f"Creating '{object_name}' with: {attributes}") # Debug
                 # Prepare constructor args (filter attributes based on __init__ if possible, otherwise pass all)
                 # For simplicity here, pass all collected valid attributes
                 constructor_args = attributes
                 obj = target_class_obj(**constructor_args)
                 self.objects[object_name] = obj
                 # Store metadata (use a copy of attributes used)
                 self.object_data[object_name] = {'class': class_name, 'attributes': constructor_args.copy()}


            self.object_name_input.clear()
            self.objects_changed.emit() # Update tree and combos
            QMessageBox.information(self, "Sukces", f"Obiekt '{object_name}' {'zaktualizowany' if is_update else 'utworzony'}.")

        except (TypeError, AttributeError, Exception) as e:
            QMessageBox.critical(self, f"Błąd {'Aktualizacji' if is_update else 'Tworzenia'}",
                                 f"Nie udało się {'zaktualizować' if is_update else 'utworzyć'} obiektu '{object_name}'.\n"
                                 f"Sprawdź zgodność typów i argumentów konstruktora.\n\nBłąd: {str(e)}")
            # Clean up if creation failed midway
            if not is_update and object_name in self.objects: del self.objects[object_name]
            if not is_update and object_name in self.object_data: del self.object_data[object_name]

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
            # Assume PyMongoConverter is in MongoDB/cassandra_converter.py relative to this script
            # You might need to adjust the import path based on your project structure
            try:
                from Converters.mongo_converter import PyMongoConverter
            except ImportError:
                 # Try importing from current directory if MongoDB folder doesn't work
                 try:
                      from main import PyMongoConverter # If cassandra_converter.py is in the same dir
                 except ImportError:
                      QMessageBox.critical(self, "Błąd Importu",
                                          "Nie znaleziono klasy 'PyMongoConverter'.\n"
                                          "Upewnij się, że plik z konwerterem (np. MongoDB/cassandra_converter.py lub cassandra_converter.py) istnieje.")
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
            # Assume PyCassandraConverter is in Cassandra/cassandra_converter.py or cassandra_converter.py
            # Adjust the import path based on your project structure
            try:
                # Adjust path as needed (e.g., 'Cassandra.converter', 'utils.cassandra_converter')
                from Converters.cassandra_converter import PyCassandraConverter
            except ImportError:
                try:
                    # If cassandra_converter.py is in the same directory or package
                    from main import PyCassandraConverter
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'PyCassandraConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. Cassandra/cassandra_converter.py lub cassandra_converter.py) istnieje.")
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
                from Converters.neo4j_converter import Neo4jConverter
            except ImportError:
                try:
                    from main import Neo4jConverter  # Try local dir
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'Neo4jConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. Neo4j/cassandra_converter.py lub cassandra_converter.py) istnieje.")
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

    def _update_object_tree(self):
        """Updates the tree view with the current state of objects."""
        self.object_tree.clear()
        sorted_object_names = sorted(self.objects.keys())

        for obj_name in sorted_object_names:
            obj_instance = self.objects.get(obj_name)
            obj_metadata = self.object_data.get(obj_name)
            if obj_instance is None or obj_metadata is None: continue # Skip inconsistent data

            obj_item = QTreeWidgetItem([obj_name])
            font = obj_item.font(0); font.setBold(True); obj_item.setFont(0, font)
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
                    attr_value_str = "<Nie ustawiono>"
                    try:
                        attr_value = getattr(obj_instance, attr_name)
                        if attr_value is None: attr_value_str = "None"
                        elif isinstance(attr_value, (str, int, float, bool)): attr_value_str = repr(attr_value)
                        elif isinstance(attr_value, (list, dict, tuple, set)):
                             repr_val = repr(attr_value)
                             attr_value_str = repr_val[:80] + ('...' if len(repr_val) > 80 else '')
                        elif isinstance(attr_value, object) and hasattr(attr_value, '__class__'):
                             found_ref_name = None
                             for ref_name, ref_instance in self.objects.items():
                                 if ref_instance is attr_value:
                                     found_ref_name = ref_name; break
                             if found_ref_name:
                                  attr_value_str = f"-> {found_ref_name} ({attr_value.__class__.__name__})"
                             else: attr_value_str = f"<{attr_value.__class__.__name__}: {str(attr_value)[:50]}>"
                        else: attr_value_str = str(attr_value)
                    except AttributeError: attr_value_str = "<Atrybut nie istnieje>"
                    except Exception as e: attr_value_str = f"<Błąd odczytu: {e}>"

                    attr_item = QTreeWidgetItem([attr_name, attr_value_str])
                    attributes_item.addChild(attr_item)

            except Exception as e:
                 attributes_item.addChild(QTreeWidgetItem([f"<Błąd przetwarzania: {e}>", ""]))

            obj_item.setExpanded(True) # Expand object node
            attributes_item.setExpanded(True) # Expand attributes node

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

    def _perform_object_connection(self, target_obj_name: str, attribute_name: str, source_obj_name: str):
        """Sets the target object's attribute to the source object."""
        try:
            target_obj = self.objects[target_obj_name]
            source_obj = self.objects.get(source_obj_name) # Use .get() as source might be "(Brak)" -> None implicitly handled later

            # Perform the connection
            print(f"Connecting: Setting {target_obj_name}.{attribute_name} = {source_obj_name if source_obj else 'None'}")
            setattr(target_obj, attribute_name, source_obj)

            # Update metadata
            if target_obj_name in self.object_data and 'attributes' in self.object_data[target_obj_name]:
                 self.object_data[target_obj_name]['attributes'][attribute_name] = source_obj # Store actual reference
                 print(f"Updated metadata for {target_obj_name}.{attribute_name}")
            else: print(f"Warning: Metadata not found/updated for {target_obj_name}")

            self.objects_changed.emit() # Update UI
            QMessageBox.information(self, "Sukces", f"Połączono: {target_obj_name}.{attribute_name} -> {source_obj_name if source_obj else 'None'}.")

        except KeyError as e: QMessageBox.critical(self, "Błąd", f"Nie znaleziono obiektu: {e}")
        except (AttributeError, TypeError, Exception) as e: QMessageBox.critical(self, "Błąd Połączenia", f"Nie udało się ustawić atrybutu.\nBłąd: {e}")


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