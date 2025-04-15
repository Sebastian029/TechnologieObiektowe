import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QFormLayout, QScrollArea,
    QSpinBox, QCheckBox, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import pyqtSignal, QLocale
from PyQt6.QtGui import QDoubleValidator
from typing import Dict, List, Optional, Any, Tuple
import random
import string
import importlib
import inspect
import ast

# --- Type Definitions ---
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any]
ObjectsDict = Dict[str, Any]


# --- Helper Functions ---
def clear_layout(layout):
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
                clear_layout(sub_layout)


# --- Dialog Classes ---
class ConnectObjectsDialog(QDialog):
    def __init__(self, objects_dict: ObjectsDict, classes_dict: ClassesDict, parent=None):
        super().__init__(parent)
        self.objects = objects_dict
        self.classes = classes_dict
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Połącz Obiekty")
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # 1. Select Target Object
        self.target_object_combo = QComboBox()
        self.target_object_combo.addItem("-- Wybierz obiekt docelowy --")
        self.target_object_combo.addItems(sorted(self.objects.keys()))
        self.target_object_combo.currentIndexChanged.connect(self._update_target_attributes)
        form_layout.addRow("Obiekt docelowy:", self.target_object_combo)

        # 2. Select Target Attribute
        self.target_attribute_combo = QComboBox()
        self.target_attribute_combo.setEnabled(False)
        self.target_attribute_combo.currentIndexChanged.connect(self._update_source_objects)
        form_layout.addRow("Atrybut docelowy:", self.target_attribute_combo)

        # 3. Select Source Object
        self.source_object_combo = QComboBox()
        self.source_object_combo.setEnabled(False)
        form_layout.addRow("Obiekt źródłowy:", self.source_object_combo)

        layout.addLayout(form_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        """Helper to get fields recursively."""
        if class_name not in self.classes:
            return []
        if visited is None:
            visited = set()
        if class_name in visited:
            return []
        visited.add(class_name)

        fields_map = {}
        parent_class = self.classes[class_name].get('inherits')
        if parent_class and parent_class in self.classes:
            parent_fields = self._get_all_fields_recursive(parent_class, visited.copy())
            for field_info in parent_fields:
                fields_map[field_info['field']['name']] = field_info

        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source_class': class_name}
        return list(fields_map.values())

    def _update_target_attributes(self):
        """Update the attribute combo based on the selected target object."""
        self.target_attribute_combo.clear()
        self.target_attribute_combo.setEnabled(False)
        self._update_source_objects()

        target_obj_name = self.target_object_combo.currentText()
        if not target_obj_name or target_obj_name.startswith("--"):
            return

        try:
            target_obj_instance = self.objects.get(target_obj_name)
            if not target_obj_instance:
                self.target_attribute_combo.addItem("-- Obiekt docelowy nie istnieje --")
                return

            target_class_name = target_obj_instance.__class__.__name__
            if target_class_name not in self.classes:
                self.target_attribute_combo.addItem("-- Klasa obiektu nieznana --")
                return

            compatible_attributes = []
            all_fields = self._get_all_fields_recursive(target_class_name)

            for field_info in all_fields:
                field = field_info['field']
                field_type_str = field['type']
                base_class_name = None

                if '[' in field_type_str and ']' in field_type_str:
                    try:
                        content = field_type_str[field_type_str.find('[') + 1:field_type_str.rfind(']')]
                        parts = [p.strip() for p in content.split(',')]
                        for part in parts:
                            if part.lower() != 'none' and part.lower() != 'nonetype':
                                potential_name = part.split('.')[-1].strip("'\" ")
                                if potential_name in self.classes:
                                    base_class_name = potential_name
                                    break
                    except Exception as e:
                        print(f"Debug: Failed to parse type string '{field_type_str}': {e}")
                        base_class_name = None
                elif field_type_str in self.classes:
                    base_class_name = field_type_str

                if base_class_name:
                    compatible_attributes.append(field['name'])

            if compatible_attributes:
                self.target_attribute_combo.addItem("-- Wybierz atrybut --")
                self.target_attribute_combo.addItems(sorted(compatible_attributes))
                self.target_attribute_combo.setEnabled(True)
            else:
                self.target_attribute_combo.addItem("-- Brak atrybutów obiektowych --")

        except KeyError:
            self.target_attribute_combo.addItem("-- Błąd pobierania klasy obiektu --")
        except Exception as e:
            self.target_attribute_combo.addItem(f"-- Błąd: {e} --")
            print(f"Error in _update_target_attributes: {e}")

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
            target_obj_instance = self.objects.get(target_obj_name)
            if not target_obj_instance:
                return

            target_class_name = target_obj_instance.__class__.__name__
            expected_base_type = None
            all_fields = self._get_all_fields_recursive(target_class_name)

            for field_info in all_fields:
                if field_info['field']['name'] == attribute_name:
                    field_type_str = field_info['field']['type']
                    if '[' in field_type_str and ']' in field_type_str:
                        try:
                            content = field_type_str[field_type_str.find('[') + 1:field_type_str.rfind(']')]
                            parts = [p.strip() for p in content.split(',')]
                            for part in parts:
                                if part.lower() != 'none' and part.lower() != 'nonetype':
                                    potential_name = part.split('.')[-1].strip("'\" ")
                                    if potential_name in self.classes:
                                        expected_base_type = potential_name
                                        break
                        except Exception:
                            pass
                    elif field_type_str in self.classes:
                        expected_base_type = field_type_str
                    break

            if not expected_base_type:
                self.source_object_combo.addItem("-- Nieznany typ atrybutu --")
                return

            compatible_sources = []
            for obj_name, obj_instance in self.objects.items():
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

        if target_obj_name.startswith("--") or \
                attribute_name.startswith("--") or \
                source_obj_name.startswith("--"):
            return None

        return target_obj_name, attribute_name, source_obj_name


# --- Main Application Classes ---
class ClassAnalyzer:
    @staticmethod
    def analyze_classes(module) -> ClassesDict:
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
                try:
                    init_sig = inspect.signature(obj.__init__)
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


class ObjectManager:
    def __init__(self, classes_dict: ClassesDict):
        self.classes = classes_dict
        self.objects: ObjectsDict = {}
        self.object_data = {}

    def get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        """Recursively gets all fields (own and inherited) for a class."""
        if class_name not in self.classes:
            return []
        if visited is None:
            visited = set()
        if class_name in visited:
            return []
        visited.add(class_name)

        fields_map: Dict[str, Dict[str, Any]] = {}

        parent_class_name = self.classes[class_name].get('inherits')
        if parent_class_name and parent_class_name in self.classes:
            parent_fields_info = self.get_all_fields_recursive(parent_class_name, visited.copy())
            for field_info in parent_fields_info:
                fields_map[field_info['field']['name']] = field_info

        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source_class': class_name}

        return list(fields_map.values())

    def create_or_update_object(self, class_name: str, object_name: str, attributes: Dict[str, Any]) -> bool:
        """Creates or updates an object with the given attributes."""
        if not class_name or class_name not in self.classes:
            return False

        is_update = object_name in self.objects
        target_class_obj = self.classes[class_name]['class_obj']

        if is_update and not isinstance(self.objects[object_name], target_class_obj):
            return False

        try:
            if is_update:
                obj = self.objects[object_name]
                for attr_name, attr_value in attributes.items():
                    setattr(obj, attr_name, attr_value)
                self.object_data[object_name]['attributes'].update(attributes)
                self.object_data[object_name]['class'] = class_name
            else:
                constructor_args = attributes
                obj = target_class_obj(**constructor_args)
                self.objects[object_name] = obj
                self.object_data[object_name] = {'class': class_name, 'attributes': constructor_args.copy()}

            return True
        except Exception:
            if not is_update and object_name in self.objects:
                del self.objects[object_name]
            if not is_update and object_name in self.object_data:
                del self.object_data[object_name]
            return False

    def delete_object(self, object_name: str) -> Tuple[bool, List[str]]:
        """Deletes an object and returns success status and list of references that were set to None."""
        if object_name not in self.objects:
            return False, []

        obj_to_delete_instance = self.objects[object_name]
        referencing_info = []

        for other_name, other_instance in self.objects.items():
            if other_name == object_name:
                continue

            try:
                other_class_name = other_instance.__class__.__name__
                if other_class_name in self.classes:
                    fields_info = self.get_all_fields_recursive(other_class_name)
                    for field_info in fields_info:
                        field = field_info['field']
                        field_type_str = field['type']

                        if self._is_object_reference_type(field_type_str):
                            try:
                                ref_value = getattr(other_instance, field['name'])
                                if ref_value is obj_to_delete_instance:
                                    referencing_info.append(f"{other_name}.{field['name']}")
                                    setattr(other_instance, field['name'], None)
                                    if other_name in self.object_data and 'attributes' in self.object_data[other_name]:
                                        if field['name'] in self.object_data[other_name]['attributes']:
                                            self.object_data[other_name]['attributes'][field['name']] = None
                            except AttributeError:
                                pass
            except Exception:
                continue

        try:
            del self.objects[object_name]
            if object_name in self.object_data:
                del self.object_data[object_name]
            return True, referencing_info
        except KeyError:
            return False, []

    def _is_object_reference_type(self, type_str: str) -> bool:
        """Determines if a type string represents an object reference type."""
        if type_str in self.classes:
            return True

        if '[' in type_str and ']' in type_str:
            try:
                content = type_str[type_str.find('[') + 1:type_str.rfind(']')]
                parts = [p.strip() for p in content.split(',')]
                for part in parts:
                    if part.lower() not in ['none', 'nonetype']:
                        class_name = part.split('.')[-1].strip("'\" ")
                        if class_name in self.classes:
                            return True
            except Exception:
                pass

        return False


class ObjectTreeManager:
    def __init__(self, tree_widget: QTreeWidget, object_manager: ObjectManager):
        self.tree = tree_widget
        self.object_manager = object_manager

    def update_tree(self):
        """Updates the tree view with the current state of objects."""
        self.tree.clear()
        sorted_object_names = sorted(self.object_manager.objects.keys())

        for obj_name in sorted_object_names:
            obj_instance = self.object_manager.objects.get(obj_name)
            obj_metadata = self.object_manager.object_data.get(obj_name)
            if obj_instance is None or obj_metadata is None:
                continue

            obj_item = QTreeWidgetItem([obj_name])
            font = obj_item.font(0)
            font.setBold(True)
            obj_item.setFont(0, font)
            self.tree.addTopLevelItem(obj_item)

            class_name = obj_instance.__class__.__name__
            class_item = QTreeWidgetItem(["Klasa", class_name])
            obj_item.addChild(class_item)

            attributes_item = QTreeWidgetItem(["Atrybuty"])
            obj_item.addChild(attributes_item)

            try:
                all_fields_info = self.object_manager.get_all_fields_recursive(class_name)
                field_names = sorted([info['field']['name'] for info in all_fields_info])

                if not field_names:
                    attributes_item.addChild(QTreeWidgetItem(["(Brak pól)", ""]))

                for attr_name in field_names:
                    attr_value_str = "<Nie ustawiono>"
                    try:
                        attr_value = getattr(obj_instance, attr_name)
                        if attr_value is None:
                            attr_value_str = "None"
                        elif isinstance(attr_value, (str, int, float, bool)):
                            attr_value_str = repr(attr_value)
                        elif isinstance(attr_value, (list, dict, tuple, set)):
                            repr_val = repr(attr_value)
                            attr_value_str = repr_val[:80] + ('...' if len(repr_val) > 80 else '')
                        elif isinstance(attr_value, object) and hasattr(attr_value, '__class__'):
                            found_ref_name = None
                            for ref_name, ref_instance in self.object_manager.objects.items():
                                if ref_instance is attr_value:
                                    found_ref_name = ref_name
                                    break
                            if found_ref_name:
                                attr_value_str = f"-> {found_ref_name} ({attr_value.__class__.__name__})"
                            else:
                                attr_value_str = f"<{attr_value.__class__.__name__}: {str(attr_value)[:50]}>"
                        else:
                            attr_value_str = str(attr_value)
                    except AttributeError:
                        attr_value_str = "<Atrybut nie istnieje>"
                    except Exception as e:
                        attr_value_str = f"<Błąd odczytu: {e}>"

                    attr_item = QTreeWidgetItem([attr_name, attr_value_str])
                    attributes_item.addChild(attr_item)

            except Exception as e:
                attributes_item.addChild(QTreeWidgetItem([f"<Błąd przetwarzania: {e}>", ""]))

            obj_item.setExpanded(True)
            attributes_item.setExpanded(True)


class ObjectFormManager:
    def __init__(self, form_layout: QFormLayout, object_manager: ObjectManager):
        self.form_layout = form_layout
        self.object_manager = object_manager
        self.field_widgets = {}

    def update_form(self, class_name: str):
        """Updates the form based on the selected class."""
        clear_layout(self.form_layout)
        self.field_widgets.clear()

        if not class_name or class_name not in self.object_manager.classes:
            if class_name:
                self.form_layout.addRow(QLabel(f"Klasa '{class_name}' nieznana."))
            return

        all_fields = self.object_manager.get_all_fields_recursive(class_name)
        if not all_fields:
            self.form_layout.addRow(QLabel("Klasa nie ma definiowanych atrybutów do wypełnienia."))
            return

        all_fields.sort(key=lambda x: x['field']['name'])

        for field_info in all_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']

            base_type = field_type
            is_optional = False
            if '[' in field_type and ']' in field_type:
                try:
                    origin_part = field_type[:field_type.find('[')]
                    content_part = field_type[field_type.find('[') + 1:field_type.rfind(']')]
                    args = [a.strip() for a in content_part.split(',')]

                    if origin_part in ['Optional', 'Union']:
                        non_none_args = [a for a in args if a.lower() != 'none' and a.lower() != 'nonetype']
                        if len(non_none_args) == 1:
                            base_type = non_none_args[0].split('.')[-1]
                        is_optional = True
                    elif origin_part in ['List', 'list', 'Dict', 'dict', 'Set', 'set', 'Tuple', 'tuple']:
                        base_type = origin_part
                except Exception:
                    pass

            label = QLabel(f"{field_name} ({field_type})")
            input_widget = None

            if base_type == "int":
                input_widget = QSpinBox()
                input_widget.setRange(-2147483647, 2147483647)
            elif base_type == "float":
                input_widget = QLineEdit()
                input_widget.setPlaceholderText("Wprowadź liczbę zmiennoprzecinkową")
                validator = QDoubleValidator()
                validator.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
                input_widget.setValidator(validator)
            elif base_type == "bool":
                input_widget = QCheckBox()
            elif base_type == "str":
                input_widget = QLineEdit()
            elif base_type in ["list", "List", "dict", "Dict", "set", "Set", "tuple", "Tuple"]:
                input_widget = QLineEdit()
                input_widget.setPlaceholderText(f"Wpisz jako Python literal (np. [1,'a'])")
                input_widget.setToolTip(f"Oczekiwany typ: {field_type}")
            elif base_type in self.object_manager.classes:
                input_widget = QComboBox()
                input_widget.addItem("(Brak)")
                for obj_name, obj_instance in self.object_manager.objects.items():
                    if obj_instance.__class__.__name__ == base_type:
                        input_widget.addItem(obj_name)
            else:
                input_widget = QLineEdit()
                input_widget.setPlaceholderText(f"(Typ: {field_type})")
                input_widget.setToolTip(f"Wprowadź wartość jako string lub Python literal dla typu: {field_type}")

            if input_widget is not None:
                self.form_layout.addRow(label, input_widget)
                self.field_widgets[field_name] = input_widget
            else:
                self.form_layout.addRow(label, QLabel(f"Nieobsługiwany typ widgetu: {field_type}"))

    def generate_random_data(self, class_name: str, name_input: QLineEdit):
        """Generates random data for the form."""
        if not class_name or class_name not in self.object_manager.classes:
            return

        if not name_input.text():
            random_name = f"{class_name.lower()}_{''.join(random.choices(string.ascii_lowercase, k=4))}"
            name_input.setText(random_name)

        for field_name, widget in self.field_widgets.items():
            if isinstance(widget, QLineEdit):
                widget.setText(''.join(random.choices(string.ascii_letters + ' ', k=10)))
            elif isinstance(widget, QSpinBox):
                widget.setValue(random.randint(widget.minimum(), min(widget.maximum(), 100)))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(random.choice([True, False]))
            elif isinstance(widget, QComboBox):
                if widget.count() > 1:
                    widget.setCurrentIndex(random.randint(1, widget.count() - 1))
                else:
                    widget.setCurrentIndex(0)

    def get_form_data(self) -> Dict[str, Any]:
        """Returns a dictionary of field names and values from the form."""
        data = {}
        for field_name, widget in self.field_widgets.items():
            if isinstance(widget, QLineEdit):
                data[field_name] = widget.text()
            elif isinstance(widget, QSpinBox):
                data[field_name] = widget.value()
            elif isinstance(widget, QCheckBox):
                data[field_name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                selected_text = widget.currentText()
                data[field_name] = None if selected_text == "(Brak)" else selected_text
        return data

    def load_object_data(self, obj_name: str, obj_instance: Any, obj_metadata: Dict[str, Any]):
        """Loads an object's data into the form."""
        class_name = obj_metadata.get('class', '')
        all_fields_info = self.object_manager.get_all_fields_recursive(class_name)

        for field_info in all_fields_info:
            field_name = field_info['field']['name']
            widget = self.field_widgets.get(field_name)
            if not widget:
                continue

            try:
                current_value = getattr(obj_instance, field_name)
            except AttributeError:
                current_value = obj_metadata.get('attributes', {}).get(field_name, None)

            if isinstance(widget, QLineEdit):
                if isinstance(current_value, (list, dict, set, tuple)):
                    try:
                        widget.setText(repr(current_value))
                    except Exception:
                        widget.setText(str(current_value))
                elif current_value is None:
                    widget.clear()
                else:
                    widget.setText(str(current_value))
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(current_value) if current_value is not None else 0)
                except (ValueError, TypeError):
                    widget.setValue(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(current_value))
            elif isinstance(widget, QComboBox):
                selected_obj_name = None
                if current_value is not None and isinstance(current_value, object):
                    for name, instance in self.object_manager.objects.items():
                        if instance is current_value:
                            selected_obj_name = name
                            break
                index = widget.findText(selected_obj_name) if selected_obj_name else -1
                widget.setCurrentIndex(index if index >= 0 else 0)


class DatabaseManager:
    @staticmethod
    def save_to_mongodb(objects: ObjectsDict):
        """Saves objects to MongoDB."""
        try:
            from Converters.mongo_converter import PyMongoConverter
            import pymongo
        except ImportError:
            try:
                from main import PyMongoConverter
            except ImportError:
                return False, "Nie znaleziono klasy 'PyMongoConverter'"

        connection_string = "mongodb://localhost:27017/"
        db_name = "object_generator_db"

        converter = None
        try:
            converter = PyMongoConverter(connection_string=connection_string, db_name=db_name)
            converter.client.admin.command('ping')

            saved_count = 0
            errors = []
            for obj_name, obj in objects.items():
                try:
                    converter.save_to_mongodb(obj)
                    saved_count += 1
                except Exception as e:
                    errors.append(f"Failed saving '{obj_name}': {str(e)}")

            if not errors:
                return True, f"Zapisano {saved_count} obiektów do MongoDB (Baza: {db_name})."
            else:
                return False, f"Zapisano {saved_count}/{len(objects)} obiektów.\n\nBłędy:\n" + "\n".join(errors)

        except pymongo.errors.ConnectionFailure as e:
            return False, f"Nie można połączyć z MongoDB.\n{e}"
        except Exception as e:
            return False, f"Wystąpił błąd: {str(e)}"
        finally:
            if converter:
                converter.close()

    @staticmethod
    def save_to_cassandra(objects: ObjectsDict):
        """Saves objects to Cassandra."""
        try:
            from Converters.cassandra_converter import PyCassandraConverter
            from cassandra.cluster import NoHostAvailable
        except ImportError:
            try:
                from main import PyCassandraConverter
            except ImportError:
                return False, "Nie znaleziono klasy 'PyCassandraConverter'"

        keyspace = "object_db"
        converter = None
        try:
            converter = PyCassandraConverter(keyspace=keyspace)

            saved_count = 0
            errors = []
            for obj_name, obj in objects.items():
                try:
                    converter.save_to_cassandra(obj)
                    saved_count += 1
                except Exception as e:
                    errors.append(f"Failed saving '{obj_name}': {str(e)}")

            if not errors:
                return True, f"Zapisano {saved_count} obiektów do Cassandra (Keyspace: {keyspace})."
            else:
                return False, f"Zapisano {saved_count}/{len(objects)} obiektów do Cassandra.\n\nBłędy:\n" + "\n".join(
                    errors)

        except NoHostAvailable as e:
            return False, f"Nie można połączyć z klastrem Cassandra.\nSprawdź ustawienia i dostępność bazy.\n{e}"
        except Exception as e:
            return False, f"Wystąpił nieoczekiwany błąd: {str(e)}"
        finally:
            if converter:
                try:
                    converter.close()
                except Exception:
                    pass

    @staticmethod
    def save_to_neo4j(objects: ObjectsDict, object_manager: ObjectManager):
        """Saves objects to Neo4j."""
        try:
            from Converters.neo4j_converter import Neo4jConverter
        except ImportError:
            try:
                from main import Neo4jConverter
            except ImportError:
                return False, "Nie znaleziono klasy 'Neo4jConverter'"

        uri = "bolt://localhost:7687"
        user = "neo4j"
        password = "password"

        converter = None
        try:
            converter = Neo4jConverter(uri=uri, user=user, password=password)
            top_level_objects = ObjectTreeManager._find_top_level_objects(objects, object_manager)

            if not top_level_objects:
                return False, "Brak obiektów najwyższego poziomu do zapisania."

            saved_count = 0
            errors = []
            for obj_name in top_level_objects:
                obj = objects[obj_name]
                try:
                    converter.save(obj)
                    saved_count += 1
                except Exception as e:
                    errors.append(f"Nie udało się zapisać '{obj_name}': {str(e)}")

            if not errors:
                return True, f"Zapisano {saved_count} obiektów najwyższego poziomu do Neo4j."
            else:
                return False, f"Zapisano {saved_count}/{len(top_level_objects)} obiektów.\n\nBłędy:\n" + "\n".join(
                    errors)

        except Exception as e:
            return False, f"Nie można połączyć z Neo4j.\n{e}"
        finally:
            if converter:
                converter.close()

    @staticmethod
    def _find_top_level_objects(objects: ObjectsDict, object_manager: ObjectManager) -> List[str]:
        """Finds objects that are not referenced by other objects."""
        referenced_objects = set()

        for obj_name, obj_instance in objects.items():
            class_name = obj_instance.__class__.__name__
            if class_name not in object_manager.classes:
                continue

            fields_info = object_manager.get_all_fields_recursive(class_name)
            for field_info in fields_info:
                field = field_info['field']
                field_type = field['type']

                if object_manager._is_object_reference_type(field_type):
                    try:
                        referenced_obj = getattr(obj_instance, field['name'])
                        if referenced_obj is not None:
                            for ref_name, ref_instance in objects.items():
                                if ref_instance is referenced_obj:
                                    referenced_objects.add(ref_name)
                                    break
                    except AttributeError:
                        pass

        return [name for name in objects.keys() if name not in referenced_objects]


# --- Main Application Window ---
class ObjectGeneratorApp(QMainWindow):
    objects_changed = pyqtSignal()

    def __init__(self, classes_module):
        super().__init__()
        self.setWindowTitle("Generator Obiektów")
        self.setGeometry(100, 100, 1000, 700)

        self.classes_module = classes_module
        self.class_analyzer = ClassAnalyzer()
        self.classes = self.class_analyzer.analyze_classes(classes_module)
        self.object_manager = ObjectManager(self.classes)
        self._setup_ui()

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
        self.object_class_combo.addItems(sorted(self.classes.keys()))
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

        # Form manager
        self.form_manager = ObjectFormManager(self.object_fields_layout, self.object_manager)

        # Generate random data button
        self.generate_data_btn = QPushButton("Wygeneruj losowe dane")
        self.generate_data_btn.clicked.connect(self._generate_random_data)
        left_layout.addWidget(self.generate_data_btn)

        # Create/Update object button
        self.create_update_object_btn = QPushButton("Utwórz/Zaktualizuj obiekt")
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

        # Tree manager
        self.tree_manager = ObjectTreeManager(self.object_tree, self.object_manager)

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

        self.save_mongodb_btn = QPushButton("MongoDB")
        self.save_mongodb_btn.clicked.connect(lambda: self._save_objects('mongodb'))
        btn_layout.addWidget(self.save_mongodb_btn)

        self.save_cassandra_btn = QPushButton("Cassandra")
        self.save_cassandra_btn.clicked.connect(lambda: self._save_objects('cassandra'))
        btn_layout.addWidget(self.save_cassandra_btn)

        self.save_neo4j_btn = QPushButton("Neo4j")
        self.save_neo4j_btn.clicked.connect(lambda: self._save_objects('neo4j'))
        btn_layout.addWidget(self.save_neo4j_btn)
        right_layout.addLayout(btn_layout)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        # Connect signals
        self.objects_changed.connect(self._update_ui)

    def _update_ui(self):
        """Updates the UI components when objects change."""
        self.tree_manager.update_tree()
        self._update_object_creation_form()

    def _update_object_creation_form(self):
        """Updates the object creation form based on the selected class."""
        selected_class = self.object_class_combo.currentText()
        self.form_manager.update_form(selected_class)

    def _generate_random_data(self):
        """Generates random data for the form."""
        selected_class = self.object_class_combo.currentText()
        self.form_manager.generate_random_data(selected_class, self.object_name_input)

    def _create_predefined_objects(self):
        """Creates predefined Book and Library objects."""
        created_objects = []
        try:
            book1, book2 = None, None
            if 'Book' in self.classes and any(f['field']['name'] == 'pages' for f in
                                              self.object_manager.get_all_fields_recursive('Book')):
                book_class = self.classes['Book']['class_obj']
                book1 = book_class(pages=200)
                self.object_manager.objects['book1'] = book1
                self.object_manager.object_data['book1'] = {'class': 'Book', 'attributes': {'pages': 200}}
                created_objects.append('book1')

                book2 = book_class(pages=350)
                self.object_manager.objects['book2'] = book2
                self.object_manager.object_data['book2'] = {'class': 'Book', 'attributes': {'pages': 350}}
                created_objects.append('book2')

            if 'Library' in self.classes and book1 and book2 and \
                    any(f['field']['name'] == 'book_obj' for f in
                        self.object_manager.get_all_fields_recursive('Library')) and \
                    any(f['field']['name'] == 'city' for f in self.object_manager.get_all_fields_recursive('Library')):
                library_class = self.classes['Library']['class_obj']
                library1 = library_class(book_obj=book1, city="Warsaw")
                self.object_manager.objects['library1'] = library1
                self.object_manager.object_data['library1'] = {'class': 'Library',
                                                               'attributes': {'book_obj': book1, 'city': "Warsaw"}}
                created_objects.append('library1')

                library2 = library_class(book_obj=book2, city="Krakow")
                self.object_manager.objects['library2'] = library2
                self.object_manager.object_data['library2'] = {'class': 'Library',
                                                               'attributes': {'book_obj': book2, 'city': "Krakow"}}
                created_objects.append('library2')

            if created_objects:
                self.objects_changed.emit()
                QMessageBox.information(self, "Sukces", f"Utworzono przykładowe obiekty: {', '.join(created_objects)}")
            else:
                QMessageBox.warning(self, "Informacja", "Nie utworzono żadnych przykładowych obiektów.")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć przykładowych obiektów: {str(e)}")

    def _create_or_update_object(self):
        """Creates or updates an object based on form data."""
        class_name = self.object_class_combo.currentText()
        object_name = self.object_name_input.text().strip()

        if not class_name or class_name not in self.classes:
            QMessageBox.warning(self, "Błąd", "Nie wybrano prawidłowej klasy.")
            return
        if not object_name:
            QMessageBox.warning(self, "Błąd", "Nazwa obiektu nie może być pusta.")
            return
        if not object_name.isidentifier() or object_name in ['None', 'True', 'False']:
            QMessageBox.warning(self, "Błąd", f"Nazwa obiektu '{object_name}' jest nieprawidłowa.")
            return

        is_update = object_name in self.object_manager.objects
        target_class_obj = self.classes[class_name]['class_obj']

        if is_update and not isinstance(self.object_manager.objects[object_name], target_class_obj):
            reply = QMessageBox.question(
                self, "Zmiana Typu Obiektu",
                f"Obiekt '{object_name}' jest typu '{self.object_manager.objects[object_name].__class__.__name__}', "
                f"a wybrano klasę '{class_name}'.\nCzy chcesz kontynuować?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        form_data = self.form_manager.get_form_data()
        attributes = {}
        conversion_errors = []
        valid_field_names = {f_info['field']['name'] for f_info in
                             self.object_manager.get_all_fields_recursive(class_name)}

        for field_name, value in form_data.items():
            if field_name not in valid_field_names:
                continue

            try:
                if isinstance(value, str):
                    label_item = None
                    for i in range(self.object_fields_layout.rowCount()):
                        item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                        if item and isinstance(item.widget(), QLabel) and field_name in item.widget().text():
                            label_item = item.widget()
                            break

                    if label_item:
                        field_type = label_item.text().split('(')[1][:-1].strip()
                        base_type = field_type.split('[')[0]

                        if not value:
                            is_optional = 'Optional' in field_type or \
                                          'Union' in field_type and \
                                          ('None' in field_type or 'NoneType' in field_type)
                            if is_optional:
                                attributes[field_name] = None
                            elif base_type == "int":
                                attributes[field_name] = 0
                            elif base_type == "float":
                                attributes[field_name] = 0.0
                            elif base_type == "bool":
                                attributes[field_name] = False
                            elif base_type in ["list", "List"]:
                                attributes[field_name] = []
                            elif base_type in ["dict", "Dict"]:
                                attributes[field_name] = {}
                            elif base_type == "str":
                                attributes[field_name] = ""
                            else:
                                attributes[field_name] = None
                        else:
                            if base_type == "int":
                                attributes[field_name] = int(value)
                            elif base_type == "float":
                                attributes[field_name] = float(value)
                            elif base_type == "bool":
                                lower_val = value.lower()
                                if lower_val in ['true', '1', 'yes', 't']:
                                    attributes[field_name] = True
                                elif lower_val in ['false', '0', 'no', 'f']:
                                    attributes[field_name] = False
                                else:
                                    raise ValueError("Oczekiwano wartości logicznej")
                            elif base_type in ["list", "List", "dict", "Dict", "set", "Set", "tuple", "Tuple"]:
                                try:
                                    attributes[field_name] = ast.literal_eval(value)
                                except (ValueError, SyntaxError) as e:
                                    raise ValueError(f"Nieprawidłowy format dla {base_type}: {e}")
                            elif base_type == "str":
                                attributes[field_name] = value
                            else:
                                attributes[field_name] = value
                else:
                    attributes[field_name] = value
            except (ValueError, TypeError) as e:
                conversion_errors.append(f"Pole '{field_name}': {e}")

        if conversion_errors:
            QMessageBox.warning(self, "Błąd danych wejściowych", "Popraw błędy:\n\n" + "\n".join(conversion_errors))
            return

        success = self.object_manager.create_or_update_object(class_name, object_name, attributes)
        if success:
            self.object_name_input.clear()
            self.objects_changed.emit()
            QMessageBox.information(
                self, "Sukces",
                f"Obiekt '{object_name}' {'zaktualizowany' if is_update else 'utworzony'}."
            )
        else:
            QMessageBox.critical(
                self, f"Błąd {'Aktualizacji' if is_update else 'Tworzenia'}",
                f"Nie udało się {'zaktualizować' if is_update else 'utworzyć'} obiektu '{object_name}'."
            )

    def _edit_selected_object(self):
        """Loads the selected object's data into the form for editing."""
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do edycji.")
            return

        item = selected_items[0]
        while item.parent():
            item = item.parent()
        object_name = item.text(0)

        if object_name not in self.object_manager.objects or object_name not in self.object_manager.object_data:
            QMessageBox.critical(self, "Błąd Wewnętrzny", f"Niespójność danych dla '{object_name}'.")
            return

        object_instance = self.object_manager.objects[object_name]
        object_metadata = self.object_manager.object_data[object_name]
        class_name = object_metadata['class']

        self.object_name_input.setText(object_name)
        class_index = self.object_class_combo.findText(class_name)
        if class_index >= 0:
            self.object_class_combo.blockSignals(True)
            self.object_class_combo.setCurrentIndex(class_index)
            self.object_class_combo.blockSignals(False)
            self._update_object_creation_form()

        QApplication.processEvents()
        self.form_manager.load_object_data(object_name, object_instance, object_metadata)
        self.raise_()
        self.activateWindow()

    def _delete_selected_object(self):
        """Deletes the selected object after confirmation."""
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do usunięcia.")
            return

        item = selected_items[0]
        while item.parent():
            item = item.parent()
        object_name = item.text(0)

        if object_name not in self.object_manager.objects:
            QMessageBox.warning(self, "Błąd", f"Nie znaleziono obiektu '{object_name}'.")
            return

        success, referencing_info = self.object_manager.delete_object(object_name)
        if success:
            message = f"Obiekt '{object_name}' został usunięty."
            if referencing_info:
                message += "\n\nReferencje ustawione na None w:\n- " + "\n- ".join(referencing_info)
            QMessageBox.information(self, "Sukces", message)
            self.objects_changed.emit()
            if self.object_name_input.text() == object_name:
                self.object_name_input.clear()
                self.object_class_combo.setCurrentIndex(-1)
                self._update_object_creation_form()
        else:
            QMessageBox.critical(self, "Błąd", f"Nie udało się usunąć obiektu '{object_name}'.")

    def _show_connect_objects_dialog(self):
        """Shows the dialog for connecting objects."""
        if not self.object_manager.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do połączenia.")
            return

        dialog = ConnectObjectsDialog(self.object_manager.objects, self.classes, self)
        if dialog.exec():
            connection_details = dialog.get_connection_details()
            if connection_details:
                target_name, attr_name, source_name = connection_details
                self._perform_object_connection(target_name, attr_name, source_name)

    def _perform_object_connection(self, target_obj_name: str, attribute_name: str, source_obj_name: str):
        """Sets the target object's attribute to the source object."""
        try:
            target_obj = self.object_manager.objects[target_obj_name]
            source_obj = self.object_manager.objects.get(source_obj_name)

            setattr(target_obj, attribute_name, source_obj)

            if target_obj_name in self.object_manager.object_data and \
                    'attributes' in self.object_manager.object_data[target_obj_name]:
                self.object_manager.object_data[target_obj_name]['attributes'][attribute_name] = source_obj

            self.objects_changed.emit()
            QMessageBox.information(
                self, "Sukces",
                f"Połączono: {target_obj_name}.{attribute_name} -> {source_obj_name if source_obj else 'None'}."
            )
        except (KeyError, AttributeError, TypeError, Exception) as e:
            QMessageBox.critical(self, "Błąd Połączenia", f"Nie udało się ustawić atrybutu.\nBłąd: {e}")

    def _save_objects(self, db_type: str):
        """Saves objects to the specified database."""
        if not self.object_manager.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
            return

        if db_type == 'mongodb':
            success, message = DatabaseManager.save_to_mongodb(self.object_manager.objects)
        elif db_type == 'cassandra':
            success, message = DatabaseManager.save_to_cassandra(self.object_manager.objects)
        elif db_type == 'neo4j':
            success, message = DatabaseManager.save_to_neo4j(self.object_manager.objects, self.object_manager)
        else:
            QMessageBox.critical(self, "Błąd", "Nieznany typ bazy danych.")
            return

        if success:
            QMessageBox.information(self, "Sukces", message)
        else:
            QMessageBox.critical(self, "Błąd", message)


# --- Application Entry Point ---
if __name__ == "__main__":
    CLASSES_MODULE_NAME = "wygenerowany_kod"
    try:
        classes_module = importlib.import_module(CLASSES_MODULE_NAME)
        print(f"Successfully imported module: {CLASSES_MODULE_NAME}")
    except ImportError:
        msg = (f"BŁĄD: Nie można zaimportować modułu '{CLASSES_MODULE_NAME}'.\n"
               f"Upewnij się, że plik '{CLASSES_MODULE_NAME}.py' istnieje w tym samym folderze.\n"
               "Aplikacja uruchomi się bez załadowanych klas.")
        print(msg)
        from types import ModuleType

        classes_module = ModuleType(CLASSES_MODULE_NAME)

    app = QApplication.instance() or QApplication(sys.argv)
    window = ObjectGeneratorApp(classes_module)
    window.show()
    sys.exit(app.exec())