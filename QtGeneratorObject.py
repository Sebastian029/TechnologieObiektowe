import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox,
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

ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any]
ObjectsDict = Dict[str, Any]


class ConnectObjectsDialog(QDialog):
    def __init__(self, objects_dict: ObjectsDict, classes_dict: ClassesDict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Połącz Obiekty")
        self.objects = objects_dict
        self.classes = classes_dict

        layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()

        self.target_object_combo = QComboBox()
        self.target_object_combo.addItem("-- Wybierz obiekt docelowy --")
        self.target_object_combo.addItems(sorted(self.objects.keys()))
        self.target_object_combo.currentIndexChanged.connect(self._update_target_attributes)
        self.form_layout.addRow("Obiekt docelowy:", self.target_object_combo)

        self.target_attribute_combo = QComboBox()
        self.target_attribute_combo.setEnabled(False)
        self.target_attribute_combo.currentIndexChanged.connect(self._update_source_widgets)
        self.form_layout.addRow("Atrybut docelowy:", self.target_attribute_combo)

        self.source_stacked_widget = QStackedWidget()
        self.source_object_combo = QComboBox()
        self.source_objects_list_widget = QListWidget()
        self.source_objects_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self.source_stacked_widget.addWidget(self.source_object_combo)
        self.source_stacked_widget.addWidget(self.source_objects_list_widget)
        self.source_stacked_widget.setEnabled(False)
        self.form_layout.addRow("Obiekt(y) źródłowe:", self.source_stacked_widget)

        layout.addLayout(self.form_layout)

        self._current_attribute_is_list = False

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _parse_field_type(self, type_str: str) -> Tuple[str, List[str]]:
        if '[' not in type_str or ']' not in type_str:
            return type_str.split('.')[-1], []

        base_type_full = type_str[:type_str.find('[')]
        content = type_str[type_str.find('[') + 1:type_str.rfind(']')]

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

    def _get_connectable_field_info(self, field_type_str: str) -> Tuple[Optional[str], str]:
        base_type_full, type_args = self._parse_field_type(field_type_str)
        base_type_simple = base_type_full.split('.')[-1].lower()

        if base_type_simple in (name.lower() for name in self.classes):
            return base_type_simple, 'single'

        if base_type_simple in ['list', 'sequence']:
            if type_args:
                item_type_arg_str = type_args[0].strip("'\" ")
                cleaned_item_type = item_type_arg_str.split('.')[-1]
                if cleaned_item_type in self.classes:
                    return cleaned_item_type, 'list'
            return None, 'none'

        if base_type_simple == 'tuple':
            if type_args:
                item_type_arg_str = type_args[0].strip("'\" ")
                if item_type_arg_str.endswith(', ...'):
                    item_type_arg_str = item_type_arg_str[:-5].strip()
                cleaned_item_type = item_type_arg_str.split('.')[-1]
                if cleaned_item_type in self.classes:
                    return cleaned_item_type, 'tuple'
            return None, 'none'

        if base_type_simple == 'set':
            if type_args:
                item_type_arg_str = type_args[0].strip("'\" ")
                cleaned_item_type = item_type_arg_str.split('.')[-1]
                if cleaned_item_type in self.classes:
                    return cleaned_item_type, 'set'
            return None, 'none'

        if base_type_simple == 'frozenset':
            if type_args:
                item_type_arg_str = type_args[0].strip("'\" ")
                cleaned_item_type = item_type_arg_str.split('.')[-1]
                if cleaned_item_type in self.classes:
                    return cleaned_item_type, 'frozenset'
            return None, 'none'

        if base_type_simple == 'tuple':
            if type_args:
                item_type_arg_str = type_args[0].strip("'\" ")
                cleaned_item_type = item_type_arg_str.split('.')[-1]
                if cleaned_item_type in self.classes:
                    return cleaned_item_type, 'tuple'
            return None, 'none'

        if base_type_simple == 'dict':
            if len(type_args) >= 2:
                key_type = type_args[0].strip("'\" ")
                value_type = type_args[1].strip("'\" ")
                cleaned_value_type = value_type.split('.')[-1]
                if cleaned_value_type in self.classes:
                    return cleaned_value_type, 'dict'
            return None, 'none'

        if base_type_simple in ['optional', 'union']:
            for arg_str in type_args:
                if arg_str.strip().lower() not in ['none', 'nonetype', 'type[none]']:
                    connectable_class, container_type = self._get_connectable_field_info(arg_str)
                    if connectable_class:
                        return connectable_class, container_type
            return None, 'none'

        return None, 'none'

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
            if potential_class_identifier in self.classes:
                return potential_class_identifier
        return None

    def _update_target_attributes(self):
        self.target_attribute_combo.clear()
        self.target_attribute_combo.setEnabled(False)
        self._update_source_widgets()

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

    def _update_source_widgets(self):
        self.source_stacked_widget.setEnabled(False)
        self.source_object_combo.clear()
        self.source_objects_list_widget.clear()

        if not hasattr(self, '_current_attribute_container_type'):
            self._current_attribute_container_type = 'none'

        target_obj_name = self.target_object_combo.currentText()
        attribute_name = self.target_attribute_combo.currentText()

        if (not target_obj_name or target_obj_name.startswith("--") or
                not attribute_name or attribute_name.startswith("--")):
            current_widget = self.source_stacked_widget.currentWidget()
            if isinstance(current_widget, QComboBox):
                current_widget.addItem("-- Najpierw wybierz atrybut --")
            elif isinstance(current_widget, QListWidget):
                item = QListWidgetItem("-- Najpierw wybierz atrybut --")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                current_widget.addItem(item)
            return

        target_obj = self.objects[target_obj_name]
        target_class_name_actual = target_obj.__class__.__name__

        expected_item_class = None
        container_type = 'none'

        all_fields_info = self._get_all_fields_recursive(target_class_name_actual)
        for field_info_item in all_fields_info:
            field_data = field_info_item['field']
            if field_data['name'] == attribute_name:
                field_type_str = field_data['type']
                if self._is_composition_field(attribute_name):
                    expected_item_class = self._get_composition_target_class(attribute_name)
                    container_type = 'single'
                else:
                    expected_item_class, container_type = self._get_connectable_field_info(field_type_str)
                break

        if not expected_item_class or container_type == 'none':
            current_widget = self.source_stacked_widget.currentWidget()
            msg = "-- Błąd: Nie można określić typu docelowego --"
            if isinstance(current_widget, QComboBox):
                current_widget.addItem(msg)
            else:
                current_widget.addItem(QListWidgetItem(msg))
            return

        self._current_attribute_container_type = container_type

        compatible_sources = []
        for obj_name, obj_instance in self.objects.items():
            if obj_name == target_obj_name:
                continue
            if obj_instance.__class__.__name__ == expected_item_class:
                compatible_sources.append(obj_name)

        compatible_sources.sort()

        if container_type in ['list', 'set', 'frozenset', 'tuple']:
            self.source_stacked_widget.setCurrentWidget(self.source_objects_list_widget)
            if compatible_sources:
                for src_name in compatible_sources:
                    item = QListWidgetItem(src_name)
                    self.source_objects_list_widget.addItem(item)
                self.source_stacked_widget.setEnabled(True)
                self.source_objects_list_widget.setEnabled(True)
            else:
                item = QListWidgetItem(f"-- Brak obiektów typu {expected_item_class} --")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
                self.source_objects_list_widget.addItem(item)
                self.source_stacked_widget.setEnabled(True)
                self.source_objects_list_widget.setEnabled(False)
        elif container_type == 'dict':
            self._setup_dict_interface(compatible_sources, expected_item_class)
        else:
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

    def _setup_dict_interface(self, compatible_sources, expected_class):
        self.source_stacked_widget.setCurrentWidget(self.source_objects_list_widget)

        self.source_objects_list_widget.clear()

        instruction_item = QListWidgetItem("-- Wybierz obiekty dla słownika --")
        instruction_item.setFlags(instruction_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
        self.source_objects_list_widget.addItem(instruction_item)

        if compatible_sources:
            for src_name in compatible_sources:
                item = QListWidgetItem(src_name)
                self.source_objects_list_widget.addItem(item)
            self.source_stacked_widget.setEnabled(True)
            self.source_objects_list_widget.setEnabled(True)
        else:
            item = QListWidgetItem(f"-- Brak obiektów typu {expected_class} --")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            self.source_objects_list_widget.addItem(item)
            self.source_stacked_widget.setEnabled(True)
            self.source_objects_list_widget.setEnabled(False)

    def get_connection_details(self) -> Optional[Tuple[str, str, Any, str]]:
        target_obj_name = self.target_object_combo.currentText()
        attribute_name = self.target_attribute_combo.currentText()

        if target_obj_name.startswith("--") or attribute_name.startswith("--"):
            return None

        container_type = getattr(self, '_current_attribute_container_type', 'single')
        source_data = None

        if container_type in ['list', 'set', 'frozenset', 'dict', 'tuple']:
            if self.source_stacked_widget.currentWidget() == self.source_objects_list_widget:
                selected_items = self.source_objects_list_widget.selectedItems()
                selected_names = [item.text() for item in selected_items
                                  if item.flags() & Qt.ItemFlag.ItemIsSelectable]

                if container_type == 'dict':
                    source_data = {f"key_{i}": name for i, name in enumerate(selected_names)}
                else:
                    source_data = selected_names
            else:
                return None
        else:
            if self.source_stacked_widget.currentWidget() == self.source_object_combo:
                source_data = self.source_object_combo.currentText()
                if source_data.startswith("--"):
                    return None
            else:
                return None

        if not source_data:
            return None

        return target_obj_name, attribute_name, source_data, container_type


class ObjectGeneratorApp(QMainWindow):
    objects_changed = pyqtSignal()

    def __init__(self, classes_module):
        super().__init__()
        self.setWindowTitle("Generator Obiektów")
        self.setGeometry(100, 100, 1000, 700)

        self.classes_module = classes_module
        self.classes = self._analyze_classes(classes_module)
        self.objects: ObjectsDict = {}
        self.object_data = {}

        self._setup_ui()
        self._update_object_class_combo()
        self._update_object_creation_form()
        self._update_object_tree()

        self.objects_changed.connect(self._update_object_tree)
        self.objects_changed.connect(self._update_composition_combos)

    def _analyze_classes(self, module) -> ClassesDict:
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
                    init_sig = inspect.signature(obj.__init__)
                    source_code = inspect.getsource(obj.__init__)

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
        composition_fields = []

        try:
            dedented_code = textwrap.dedent(source_code)

            lines = dedented_code.split('\n')
            if lines and lines[0].strip().startswith('def '):
                clean_code = dedented_code
            else:
                clean_code = "if True:\n" + textwrap.indent(dedented_code, "    ")

            tree = ast.parse(clean_code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Attribute) and
                                isinstance(target.value, ast.Name) and
                                target.value.id == 'self'):

                            attr_name = target.attr

                            if isinstance(node.value, ast.Call):
                                class_name = None
                                if isinstance(node.value.func, ast.Name):
                                    class_name = node.value.func.id
                                elif isinstance(node.value.func, ast.Attribute):
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
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout(left_panel)

        class_layout = QHBoxLayout()
        class_layout.addWidget(QLabel("Klasa:"))
        self.object_class_combo = QComboBox()
        self.object_class_combo.currentIndexChanged.connect(self._update_object_creation_form)
        class_layout.addWidget(self.object_class_combo)
        left_layout.addLayout(class_layout)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nazwa obiektu:"))
        self.object_name_input = QLineEdit()
        name_layout.addWidget(self.object_name_input)
        left_layout.addLayout(name_layout)

        left_layout.addWidget(QLabel("Atrybuty:"))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.fields_form_widget = QWidget()
        self.object_fields_layout = QFormLayout(self.fields_form_widget)
        self.object_fields_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_area.setWidget(self.fields_form_widget)
        left_layout.addWidget(self.scroll_area)

        self.generate_data_btn = QPushButton("Wygeneruj losowe dane")
        self.generate_data_btn.clicked.connect(self._generate_random_data)
        left_layout.addWidget(self.generate_data_btn)

        self.create_update_object_btn = QPushButton("Utwórz/Zaktualizuj obiekt")
        self.create_update_object_btn.clicked.connect(self._create_or_update_object)
        left_layout.addWidget(self.create_update_object_btn)

        self.create_predefined_btn = QPushButton("Utwórz przykładowe obiekty")
        self.create_predefined_btn.clicked.connect(self._create_predefined_objects)
        left_layout.addWidget(self.create_predefined_btn)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Istniejące obiekty:"))
        self.object_tree = QTreeWidget()
        self.object_tree.setHeaderLabels(["Właściwość", "Wartość"])
        self.object_tree.setColumnWidth(0, 200)
        right_layout.addWidget(self.object_tree)

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
        self.save_mongodb_btn.clicked.connect(self._save_objects_to_mongodb)
        btn_layout.addWidget(self.save_mongodb_btn)

        self.save_cassandra_btn = QPushButton("Cassandra")
        self.save_cassandra_btn.clicked.connect(self._save_objects_to_cassandra)
        btn_layout.addWidget(self.save_cassandra_btn)

        self.save_neo4j_btn = QPushButton("Neo4j")
        self.save_neo4j_btn.clicked.connect(self._save_objects_to_neo4j)
        btn_layout.addWidget(self.save_neo4j_btn)
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

    def _update_object_class_combo(self):
        self.object_class_combo.clear()
        self.object_class_combo.addItems(sorted(self.classes.keys()))
        self.object_class_combo.setCurrentIndex(-1)

    def _clear_layout(self, layout):
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
        self._clear_layout(self.object_fields_layout)

        selected_class = self.object_class_combo.currentText()
        if not selected_class or selected_class not in self.classes:
            if selected_class:
                self.object_fields_layout.addRow(QLabel(f"Klasa '{selected_class}' nieznana."))
            return

        all_fields = self._get_all_fields_recursive(selected_class)
        all_fields.sort(key=lambda x: x['field']['name'])

        composition_groups = {}
        regular_fields = []

        for field_info in all_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']

            if field_type in self.classes:
                comp_class_fields = self._get_all_fields_recursive(field_type)
                if field_type not in composition_groups:
                    composition_groups[field_type] = {
                        'attribute_name': field_name,
                        'fields': comp_class_fields
                    }
            else:
                regular_fields.append(field_info)

        for field_info in regular_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']

            label = QLabel(f"{field_name} ({field_type})")
            input_widget = self._create_input_widget(field_type)

            if input_widget:
                self.object_fields_layout.addRow(label, input_widget)

        for comp_type, comp_info in composition_groups.items():
            separator_label = QLabel(f"=== Kompozycja: {comp_info['attribute_name']} ({comp_type}) ===")
            font = separator_label.font()
            font.setBold(True)
            separator_label.setFont(font)
            self.object_fields_layout.addRow(separator_label)

            for comp_field_info in comp_info['fields']:
                comp_field = comp_field_info['field']
                comp_field_name = comp_field['name']
                comp_field_type = comp_field['type']

                prefixed_name = f"{comp_type.lower()}_{comp_field_name}"

                label = QLabel(f"{prefixed_name} ({comp_field_type})")
                input_widget = self._create_input_widget(comp_field_type)

                if input_widget:
                    self.object_fields_layout.addRow(label, input_widget)

    def _create_input_widget(self, field_type: str):
        normalized_type = field_type.replace("FrozenSet", "Set").replace("frozenset", "set")
        normalized_type = normalized_type.replace("Tuple", "List").replace("tuple", "list")

        if normalized_type == "complex":
            input_widget = QLineEdit()
            input_widget.setPlaceholderText("Wpisz liczbę zespoloną (np. complex(3, 4) lub 3+4j)")
        elif normalized_type in ["List[complex]", "Set[complex]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(
                f"Wpisz {normalized_type.lower()} jako Python literal (np. [complex(1,2), complex(3,4)])")
        elif normalized_type == "Dict[str, complex]":
            input_widget = QLineEdit()
            input_widget.setPlaceholderText("Wpisz słownik z liczbami zespolonymi (np. {'key1': complex(1,2)})")
        elif normalized_type.startswith("Optional[complex"):
            input_widget = QLineEdit()
            input_widget.setPlaceholderText("Wpisz liczbę zespoloną lub None (np. complex(3,4) lub None)")
        elif normalized_type in ["List[float]", "List[int]", "List[str]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"Wpisz listę jako Python literal (np. [1.0, 2.0] dla List[float])")
        elif normalized_type in ["Dict[str, str]", "Dict[str, int]", "Dict[str, float]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"Wpisz słownik jako Python literal (np. {{'klucz': wartość}})")
        elif normalized_type in ["Set[int]", "Set[float]", "Set[str]"]:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"Wpisz zbiór jako Python literal (np. {{1, 2, 3}})")
        elif normalized_type.startswith("List[") and normalized_type.endswith("]"):
            inner_type = normalized_type[5:-1]
            input_widget = QLineEdit()
            if inner_type in self.classes:
                input_widget.setPlaceholderText(f"Wpisz listę nazw obiektów typu {inner_type} (np. ['obj1', 'obj2'])")
            else:
                input_widget.setPlaceholderText(f"Wpisz listę jako Python literal")
        elif normalized_type.startswith("Set[") and normalized_type.endswith("]"):
            inner_type = normalized_type[4:-1]
            input_widget = QLineEdit()
            if inner_type in self.classes:
                input_widget.setPlaceholderText(f"Wpisz zbiór nazw obiektów typu {inner_type} (np. {{'obj1', 'obj2'}})")
            else:
                input_widget.setPlaceholderText(f"Wpisz zbiór jako Python literal")
        elif normalized_type.startswith("Dict[str, ") and normalized_type.endswith("]"):
            value_type = normalized_type[10:-1]
            input_widget = QLineEdit()
            if value_type in self.classes:
                input_widget.setPlaceholderText(
                    f"Wpisz słownik z obiektami typu {value_type} (np. {{'key': 'obj_name'}})")
            else:
                input_widget.setPlaceholderText(f"Wpisz słownik jako Python literal")
        elif normalized_type.startswith("Optional[") and normalized_type.endswith("]"):
            inner_type = normalized_type[9:-1]
            if inner_type in self.classes:
                input_widget = QComboBox()
                input_widget.addItem("None")
                for obj_name, obj_instance in self.objects.items():
                    if obj_instance.__class__.__name__ == inner_type:
                        input_widget.addItem(obj_name)
            else:
                input_widget = QLineEdit()
                input_widget.setPlaceholderText(f"Wpisz wartość typu {inner_type} lub None")
        elif normalized_type == "float":
            input_widget = QLineEdit()
            validator = QDoubleValidator()
            validator.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
            input_widget.setValidator(validator)
        elif normalized_type == "int":
            input_widget = QSpinBox()
            input_widget.setRange(-2147483647, 2147483647)
        elif normalized_type == "bool":
            input_widget = QCheckBox()
        elif normalized_type == "str":
            input_widget = QLineEdit()
        elif normalized_type in self.classes:
            input_widget = QComboBox()
            input_widget.addItem("(Brak)")
            for obj_name, obj_instance in self.objects.items():
                if obj_instance.__class__.__name__ == normalized_type:
                    input_widget.addItem(obj_name)
        else:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"(Typ: {field_type})")

        return input_widget

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        if class_name not in self.classes:
            return []
        if visited is None: visited = set()
        if class_name in visited: return []
        visited.add(class_name)

        fields_map: Dict[str, Dict[str, Any]] = {}

        parent_class_name = self.classes[class_name].get('inherits')
        if parent_class_name and parent_class_name in self.classes:
            parent_fields_info = self._get_all_fields_recursive(parent_class_name, visited.copy())
            for field_info in parent_fields_info:
                fields_map[field_info['field']['name']] = field_info

        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source_class': class_name}

        return list(fields_map.values())

    def _generate_random_data(self):
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

            normalized_type = field_type.replace("FrozenSet", "Set").replace("frozenset", "set")
            normalized_type = normalized_type.replace("Tuple", "List").replace("tuple", "list")

            if isinstance(field_widget, QLineEdit):
                if normalized_type == "complex":
                    real_part = round(random.uniform(-100, 100), 2)
                    imag_part = round(random.uniform(-100, 100), 2)
                    field_widget.setText(f"complex({real_part}, {imag_part})")
                elif normalized_type == "List[complex]":
                    complex_list = []
                    for _ in range(3):
                        real_part = round(random.uniform(-100, 100), 2)
                        imag_part = round(random.uniform(-100, 100), 2)
                        complex_list.append(f"complex({real_part}, {imag_part})")
                    field_widget.setText(f"[{', '.join(complex_list)}]")
                elif normalized_type == "Set[complex]":
                    complex_set = []
                    for _ in range(3):
                        real_part = round(random.uniform(-100, 100), 2)
                        imag_part = round(random.uniform(-100, 100), 2)
                        complex_set.append(f"complex({real_part}, {imag_part})")
                    field_widget.setText(f"{{{', '.join(complex_set)}}}")
                elif normalized_type == "Dict[str, complex]":
                    complex_dict = {}
                    for i in range(2):
                        real_part = round(random.uniform(-100, 100), 2)
                        imag_part = round(random.uniform(-100, 100), 2)
                        complex_dict[f"key_{i}"] = f"complex({real_part}, {imag_part})"
                    field_widget.setText(str(complex_dict))
                elif normalized_type.startswith("Optional[complex"):
                    if random.choice([True, False]):
                        real_part = round(random.uniform(-100, 100), 2)
                        imag_part = round(random.uniform(-100, 100), 2)
                        field_widget.setText(f"complex({real_part}, {imag_part})")
                    else:
                        field_widget.setText("None")
                elif normalized_type == "List[float]":
                    field_widget.setText(str([round(random.uniform(0, 100), 2) for _ in range(3)]))
                elif normalized_type == "List[int]":
                    field_widget.setText(str([random.randint(1, 100) for _ in range(3)]))
                elif normalized_type == "List[str]":
                    field_widget.setText(str([''.join(random.choices(string.ascii_letters, k=5)) for _ in range(3)]))
                elif normalized_type.startswith("List[") and normalized_type.endswith("]"):
                    inner_type = normalized_type[5:-1]
                    if inner_type in self.classes:
                        compatible_objects = [name for name, obj in self.objects.items()
                                              if obj.__class__.__name__ == inner_type]
                        if compatible_objects:
                            selected_objects = random.sample(compatible_objects, min(2, len(compatible_objects)))
                            field_widget.setText(str(selected_objects))
                        else:
                            field_widget.setText("[]")
                    else:
                        field_widget.setText("[]")
                elif normalized_type == "Dict[str, str]":
                    field_widget.setText(
                        str({f"key_{i}": ''.join(random.choices(string.ascii_letters, k=5)) for i in range(2)}))
                elif normalized_type == "Dict[str, int]":
                    field_widget.setText(str({f"key_{i}": random.randint(1, 100) for i in range(2)}))
                elif normalized_type == "Dict[str, float]":
                    field_widget.setText(str({f"key_{i}": round(random.uniform(1, 100), 2) for i in range(2)}))
                elif normalized_type.startswith("Dict[str, ") and normalized_type.endswith("]"):
                    value_type = normalized_type[10:-1]
                    if value_type in self.classes:
                        compatible_objects = [name for name, obj in self.objects.items()
                                              if obj.__class__.__name__ == value_type]
                        if compatible_objects:
                            field_widget.setText(str({f"key_{i}": random.choice(compatible_objects) for i in range(2)}))
                        else:
                            field_widget.setText("{}")
                    else:
                        field_widget.setText("{}")
                elif normalized_type in ["Set[int]"]:
                    field_widget.setText(str({random.randint(1, 100) for _ in range(3)}))
                elif normalized_type in ["Set[float]"]:
                    field_widget.setText(str({round(random.uniform(1, 100), 2) for _ in range(3)}))
                elif normalized_type in ["Set[str]"]:
                    field_widget.setText(str({''.join(random.choices(string.ascii_letters, k=5)) for _ in range(3)}))
                elif normalized_type.startswith("Set[") and normalized_type.endswith("]"):
                    inner_type = normalized_type[4:-1]
                    if inner_type in self.classes:
                        compatible_objects = [name for name, obj in self.objects.items()
                                              if obj.__class__.__name__ == inner_type]
                        if compatible_objects:
                            selected_objects = random.sample(compatible_objects, min(2, len(compatible_objects)))
                            field_widget.setText(str(set(selected_objects)))
                        else:
                            field_widget.setText("set()")
                    else:
                        field_widget.setText("set()")
                elif normalized_type.startswith("Optional[") and normalized_type.endswith("]"):
                    inner_type = normalized_type[9:-1]
                    if inner_type in self.classes:
                        compatible_objects = [name for name, obj in self.objects.items()
                                              if obj.__class__.__name__ == inner_type]
                        if compatible_objects and random.choice([True, False]):
                            field_widget.setText(random.choice(compatible_objects))
                        else:
                            field_widget.setText("None")
                    elif inner_type == "str":
                        field_widget.setText(''.join(random.choices(string.ascii_letters + ' ', k=10)) if random.choice(
                            [True, False]) else "None")
                    elif inner_type == "int":
                        field_widget.setText(str(random.randint(1, 100)) if random.choice([True, False]) else "None")
                    elif inner_type == "float":
                        field_widget.setText(
                            f"{random.uniform(0, 100):.2f}" if random.choice([True, False]) else "None")
                    else:
                        field_widget.setText("None")
                elif normalized_type == "float":
                    field_widget.setText(f"{random.uniform(0, 100):.2f}")
                elif normalized_type == "str":
                    field_widget.setText(''.join(random.choices(string.ascii_letters + ' ', k=10)))
                else:
                    field_widget.setText("random_val")
            elif isinstance(field_widget, QSpinBox):
                field_widget.setValue(random.randint(field_widget.minimum(), min(field_widget.maximum(), 100)))
            elif isinstance(field_widget, QCheckBox):
                field_widget.setChecked(random.choice([True, False]))
            elif isinstance(field_widget, QComboBox):
                if field_widget.count() > 1:
                    field_widget.setCurrentIndex(random.randint(1, field_widget.count() - 1))
                else:
                    field_widget.setCurrentIndex(0)

    def _create_predefined_objects(self):
        created_objects = []

        for class_name, class_info in self.classes.items():
            for i in range(1, 3):
                obj_name = f"{class_name.lower()}_{i}"
                if obj_name in self.objects:
                    continue

                constructor_args = {}
                fields_info = self._get_all_fields_recursive(class_name)

                for field_info in fields_info:
                    field = field_info['field']
                    field_name = field['name']
                    field_type = field['type']

                    if field_type == "int":
                        constructor_args[field_name] = random.randint(1, 100)
                    elif field_type == "float":
                        constructor_args[field_name] = round(random.uniform(1, 100), 2)
                    elif field_type == "bool":
                        constructor_args[field_name] = random.choice([True, False])
                    elif field_type == "str":
                        constructor_args[field_name] = ''.join(random.choices(string.ascii_letters, k=10))
                    elif field_type == "complex":
                        constructor_args[field_name] = complex(random.uniform(1, 100), random.uniform(1, 100))
                    elif field_type == "List[complex]":
                        constructor_args[field_name] = [complex(random.uniform(1, 100), random.uniform(1, 100)) for _ in
                                                        range(3)]
                    elif field_type == "Set[complex]":
                        values = {complex(random.uniform(1, 100), random.uniform(1, 100)) for _ in range(3)}
                        constructor_args[field_name] = values
                    elif field_type == "Dict[str, complex]":
                        constructor_args[field_name] = {
                            f"key_{i}": complex(random.uniform(1, 100), random.uniform(1, 100))
                            for i in range(2)
                        }
                    elif field_type.startswith("Optional[complex"):
                        if random.choice([True, False]):
                            constructor_args[field_name] = complex(random.uniform(1, 100), random.uniform(1, 100))
                        else:
                            constructor_args[field_name] = None
                    elif field_type.startswith("List["):
                        element_type = field_type[5:-1]
                        if element_type == "int":
                            constructor_args[field_name] = [random.randint(1, 100) for _ in range(3)]
                        elif element_type == "float":
                            constructor_args[field_name] = [round(random.uniform(1, 100), 2) for _ in range(3)]
                        elif element_type == "str":
                            constructor_args[field_name] = [''.join(random.choices(string.ascii_letters, k=5)) for _ in
                                                            range(3)]
                        else:
                            compatible_objects = [obj for name, obj in self.objects.items()
                                                  if obj.__class__.__name__ == element_type]
                            if compatible_objects:
                                constructor_args[field_name] = random.sample(compatible_objects,
                                                                             min(3, len(compatible_objects)))
                            else:
                                constructor_args[field_name] = []
                    elif field_type.startswith("Tuple[") or field_type.startswith("tuple["):
                        inner_content = field_type[field_type.find('[') + 1:field_type.rfind(']')]
                        if "," in inner_content:
                            types = [t.strip() for t in inner_content.split(',')]
                            tuple_values = []
                            for t in types:
                                if t == "int":
                                    tuple_values.append(random.randint(1, 100))
                                elif t == "float":
                                    tuple_values.append(round(random.uniform(1, 100), 2))
                                elif t == "str":
                                    tuple_values.append(''.join(random.choices(string.ascii_letters, k=5)))

                            constructor_args[field_name] = tuple(tuple_values)
                        else:
                            element_type = inner_content.replace("...", "").strip()
                            if element_type == "int":
                                constructor_args[field_name] = tuple([random.randint(1, 100) for _ in range(3)])
                            elif element_type == "str":
                                constructor_args[field_name] = tuple(
                                    [''.join(random.choices(string.ascii_letters, k=5)) for _ in range(3)])
                            else:
                                constructor_args[field_name] = ()
                    elif field_type.startswith("Set[") or field_type.startswith("FrozenSet["):
                        element_type = field_type[field_type.find('[') + 1:field_type.rfind(']')]
                        if element_type == "int":
                            values = {random.randint(1, 100) for _ in range(3)}
                            constructor_args[field_name] = frozenset(values) if "FrozenSet" in field_type else values
                        elif element_type == "str":
                            values = {''.join(random.choices(string.ascii_letters, k=5)) for _ in range(3)}
                            constructor_args[field_name] = frozenset(values) if "FrozenSet" in field_type else values
                        else:
                            constructor_args[field_name] = frozenset() if "FrozenSet" in field_type else set()
                    elif field_type.startswith("Dict["):
                        key_type, value_type = field_type[5:-1].split(",", 1)
                        key_type = key_type.strip()
                        value_type = value_type.strip()

                        if value_type in self.classes:
                            compatible_objects = [name for name, obj in self.objects.items()
                                                  if obj.__class__.__name__ == value_type]
                            if compatible_objects:
                                constructor_args[field_name] = {
                                    f"key_{i}": random.choice(compatible_objects)
                                    for i in range(2)
                                }
                            else:
                                constructor_args[field_name] = {}
                        else:
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

                    elif field_type.startswith("Optional["):
                        inner_type = field_type[9:-1]
                        if random.choice([True, False]):
                            constructor_args[field_name] = None
                        else:
                            if inner_type == "int":
                                constructor_args[field_name] = random.randint(1, 100)
                            elif inner_type == "str":
                                constructor_args[field_name] = ''.join(random.choices(string.ascii_letters, k=10))
                            elif inner_type in self.classes:
                                compatible_objects = [obj for name, obj in self.objects.items()
                                                      if obj.__class__.__name__ == inner_type]
                                if compatible_objects:
                                    constructor_args[field_name] = random.choice(compatible_objects)
                                else:
                                    constructor_args[field_name] = None
                            else:
                                constructor_args[field_name] = None
                    elif field_type in self.classes:
                        compatible_objects = [obj for name, obj in self.objects.items()
                                              if obj.__class__.__name__ == field_type]
                        if compatible_objects:
                            constructor_args[field_name] = random.choice(compatible_objects)
                        else:
                            constructor_args[field_name] = None
                    else:
                        if "list" in field_type.lower():
                            constructor_args[field_name] = []
                        elif "tuple" in field_type.lower():
                            constructor_args[field_name] = ()
                        elif "set" in field_type.lower():
                            constructor_args[field_name] = set()
                        elif "dict" in field_type.lower():
                            constructor_args[field_name] = {}
                        else:
                            constructor_args[field_name] = None

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
        class_name = self.object_class_combo.currentText()
        object_name = self.object_name_input.text().strip()

        if not class_name or class_name not in self.classes:
            QMessageBox.warning(self, "Błąd", "Nie wybrano prawidłowej klasy.")
            return
        if not object_name:
            QMessageBox.warning(self, "Błąd", "Nazwa obiektu nie może być pusta.")
            return

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

            value = None
            try:
                if isinstance(field_widget, QLineEdit):
                    text_value = field_widget.text().strip()
                    if text_value:
                        if field_type == "int":
                            value = int(text_value)
                        elif field_type == "complex":
                            try:
                                value = eval(text_value)
                                if not isinstance(value, complex):
                                    raise ValueError("Nie jest liczbą zespoloną")
                            except:
                                if "complex(" in text_value:
                                    import re
                                    match = re.search(r'complex\(([^,]+),\s*([^)]+)\)', text_value)
                                    if match:
                                        real_part = float(match.group(1))
                                        imag_part = float(match.group(2))
                                        value = complex(real_part, imag_part)
                                    else:
                                        raise ValueError("Nieprawidłowy format complex()")
                                elif "j" in text_value or "J" in text_value:
                                    value = complex(text_value)
                                else:
                                    real_part = float(text_value)
                                    value = complex(real_part, 0)
                        elif field_type == "float":
                            value = float(text_value)
                        elif field_type == "str":
                            value = text_value
                        elif field_type.startswith("List[") or field_type.startswith("Tuple[") or field_type.startswith(
                                "Set[") or field_type.startswith("FrozenSet[") or field_type.startswith(
                            "Dict[") or field_type.startswith("Optional["):
                            try:
                                if text_value.lower() == "none":
                                    value = None
                                else:
                                    if not self._validate_input_format(text_value, field_type):
                                        raise ValueError(f"Nieprawidłowy format dla typu {field_type}")

                                    evaluated_value = eval(text_value)

                                    if field_type.startswith("List["):
                                        inner_type = field_type[5:-1]
                                        if inner_type in self.classes and isinstance(evaluated_value, list):
                                            value = [self.objects.get(name, name) for name in evaluated_value]
                                        else:
                                            value = evaluated_value
                                    elif field_type.startswith("Set[") or field_type.startswith("FrozenSet["):
                                        inner_type = field_type[field_type.find('[') + 1:field_type.rfind(']')]
                                        if inner_type in self.classes and isinstance(evaluated_value, (set, frozenset)):
                                            converted_set = {self.objects.get(name, name) for name in evaluated_value}
                                            value = frozenset(converted_set) if field_type.startswith(
                                                "FrozenSet") else converted_set
                                        else:
                                            value = evaluated_value
                                    elif field_type.startswith("Dict[str,") or field_type.startswith("Dict[str, "):
                                        try:
                                            if text_value.lower() == "none":
                                                value = None
                                            else:
                                                evaluated_value = eval(text_value)
                                                import re
                                                value_type_match = re.search(r'Dict\[str,\s*([^\]]+)\]', field_type)
                                                if value_type_match:
                                                    value_type = value_type_match.group(1).strip()
                                                    if value_type in self.classes and isinstance(evaluated_value, dict):
                                                        validated_dict = {}
                                                        for k, v in evaluated_value.items():
                                                            if not isinstance(k, str):
                                                                raise ValueError(f"Klucz '{k}' musi być typu string")
                                                            if v not in self.objects:
                                                                raise ValueError(f"Obiekt '{v}' nie istnieje")
                                                            validated_dict[k] = self.objects[v]
                                                        value = validated_dict
                                                    else:
                                                        value = evaluated_value
                                                else:
                                                    value = evaluated_value
                                        except Exception as e:
                                            raise ValueError(f"Nieprawidłowy format słownika: {e}")
                                    else:
                                        value = evaluated_value
                            except Exception as e:
                                raise ValueError(f"Nieprawidłowy format danych: {e}")
                        else:
                            if field_type in self.classes and text_value in self.objects:
                                value = self.objects[text_value]
                            else:
                                value = text_value
                    else:
                        if field_type == "str":
                            value = ""
                        elif field_type in ["int", "float", "complex"]:
                            value = None
                        elif field_type == "bool":
                            value = False
                        elif field_type.startswith("List["):
                            value = []
                        elif field_type.startswith("Tuple["):
                            value = ()
                        elif field_type.startswith("Set["):
                            value = set()
                        elif field_type.startswith("FrozenSet["):
                            value = frozenset()
                        elif field_type.startswith("Dict["):
                            value = {}
                        else:
                            value = None

                elif isinstance(field_widget, QSpinBox):
                    value = field_widget.value()
                elif isinstance(field_widget, QCheckBox):
                    value = field_widget.isChecked()
                elif isinstance(field_widget, QComboBox):
                    selected_text = field_widget.currentText()
                    if selected_text in ["(Brak)", "None", ""]:
                        value = None
                    else:
                        if selected_text in self.objects:
                            value = self.objects[selected_text]
                        else:
                            value = selected_text

                form_data[field_name] = value

            except (ValueError, TypeError) as e:
                conversion_errors.append(f"Pole '{field_name}' ({field_type}): {e}")

        if conversion_errors:
            QMessageBox.warning(self, "Błąd danych wejściowych", "Popraw błędy:\n\n" + "\n".join(conversion_errors))
            return

        constructor_args = self._prepare_constructor_args(class_name, form_data)

        try:
            is_update = object_name in self.objects

            if is_update:
                obj = self.objects[object_name]
                for attr_name, attr_value in constructor_args.items():
                    setattr(obj, attr_name, attr_value)
                self.object_data[object_name]['attributes'] = constructor_args.copy()
            else:
                obj = self.classes[class_name]['class_obj'](**constructor_args)
                self.objects[object_name] = obj
                self.object_data[object_name] = {'class': class_name, 'attributes': constructor_args.copy()}

            self.object_name_input.clear()
            if hasattr(self, '_clear_object_form'):
                self._clear_object_form()
            self.objects_changed.emit()

            action = "zaktualizowany" if is_update else "utworzony"
            QMessageBox.information(self, "Sukces", f"Obiekt '{object_name}' został {action} pomyślnie.")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć/zaktualizować obiektu: {e}")

    def _validate_input_format(self, text_value, field_type):
        try:
            if field_type.startswith("Dict["):
                if not (text_value.strip().startswith('{') and text_value.strip().endswith('}')):
                    return False
            elif field_type.startswith("List["):
                if not (text_value.strip().startswith('[') and text_value.strip().endswith(']')):
                    return False
            elif field_type.startswith("Set["):
                if not (text_value.strip().startswith('{') and text_value.strip().endswith('}')):
                    return False
            return True
        except Exception:
            return False

    def _prepare_constructor_args(self, class_name: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        constructor_args = {}

        try:
            class_obj = self.classes[class_name]['class_obj']
            init_sig = inspect.signature(class_obj.__init__)

            for param_name, param in init_sig.parameters.items():
                if param_name == 'self':
                    continue

                if param_name in form_data:
                    constructor_args[param_name] = form_data[param_name]
                else:
                    potential_prefix = f"{class_name.lower()}_"
                    matching_fields = {k: v for k, v in form_data.items()
                                       if k.startswith(potential_prefix)}

                    if matching_fields:
                        clean_param = param_name.replace(potential_prefix, "")
                        if f"{potential_prefix}{clean_param}" in form_data:
                            constructor_args[param_name] = form_data[f"{potential_prefix}{clean_param}"]

                    if param_name not in constructor_args:
                        param_type_str = str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any"
                        param_type_name = param_type_str.split('.')[-1]

                        for field_name, field_value in form_data.items():
                            if param_type_name.lower() in field_name.lower():
                                constructor_args[param_name] = field_value
                                break

                        if param_name not in constructor_args:
                            if param.default != inspect.Parameter.empty:
                                constructor_args[param_name] = param.default
                            else:
                                for field_name, field_value in form_data.items():
                                    if param_name in field_name or field_name in param_name:
                                        constructor_args[param_name] = field_value
                                        break

        except Exception as e:
            print(f"Błąd podczas przygotowywania argumentów konstruktora: {e}")
            constructor_args = form_data.copy()

        return constructor_args

    def _is_composition_field_type(self, field_type: str) -> bool:
        return field_type in self.classes

    def _extract_composition_param_name(self, field_name: str, class_type: str) -> str:
        class_prefix = class_type.lower() + "_"
        if field_name.startswith(class_prefix):
            return field_name[len(class_prefix):]
        return field_name

    def _find_composition_attribute_name(self, class_name: str, comp_type: str) -> str:
        if class_name not in self.classes:
            return None

        fields = self.classes[class_name].get('fields', [])
        for field in fields:
            if field['type'] == comp_type:
                return field['name']
        return None

    def _edit_selected_object(self):
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do edycji.")
            return

        item = selected_items[0]
        while item.parent(): item = item.parent()
        object_name = item.text(0)

        if object_name not in self.objects or object_name not in self.object_data:
            QMessageBox.critical(self, "Błąd Wewnętrzny", f"Niespójność danych dla '{object_name}'.")
            return

        object_instance = self.objects[object_name]
        object_metadata = self.object_data[object_name]
        class_name = object_metadata['class']

        self.object_name_input.setText(object_name)

        class_index = self.object_class_combo.findText(class_name)
        if class_index >= 0:
            self.object_class_combo.blockSignals(True)
            self.object_class_combo.setCurrentIndex(class_index)
            self.object_class_combo.blockSignals(False)
            self._update_object_creation_form()
        else:
            QMessageBox.warning(self, "Ostrzeżenie", f"Klasa '{class_name}' obiektu nie znaleziona.")
            self._update_object_creation_form()

        QApplication.processEvents()

        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not label_item or not field_item: continue
            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if not isinstance(label_widget, QLabel) or not field_widget: continue

            try:
                field_name = label_widget.text().split('(')[0].strip()
            except Exception:
                continue

            try:
                current_value = getattr(object_instance, field_name)
            except AttributeError:
                current_value = object_metadata.get('attributes', {}).get(field_name, None)
                print(f"Info: Attr '{field_name}' not on instance, using metadata for edit.")
            except Exception as e:
                current_value = f"<Błąd odczytu: {e}>"

            if isinstance(field_widget, QLineEdit):
                if isinstance(current_value, (list, dict, set, tuple)):
                    try:
                        field_widget.setText(repr(current_value))
                    except Exception:
                        field_widget.setText(str(current_value))
                elif current_value is None:
                    field_widget.clear()
                else:
                    field_widget.setText(str(current_value))
            elif isinstance(field_widget, QSpinBox):
                try:
                    field_widget.setValue(int(current_value) if current_value is not None else 0)
                except (ValueError, TypeError):
                    field_widget.setValue(0)
            elif isinstance(field_widget, QCheckBox):
                field_widget.setChecked(bool(current_value))
            elif isinstance(field_widget, QComboBox):
                selected_obj_name = None
                if current_value is not None and isinstance(current_value, object):
                    for name, instance in self.objects.items():
                        if instance is current_value:
                            selected_obj_name = name
                            break
                index = field_widget.findText(selected_obj_name) if selected_obj_name else -1
                field_widget.setCurrentIndex(index if index >= 0 else 0)

        self.raise_()
        self.activateWindow()

    def _delete_selected_object(self):
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do usunięcia.")
            return

        item = selected_items[0]
        while item.parent():
            item = item.parent()
        object_name = item.text(0)

        if object_name not in self.objects:
            QMessageBox.warning(self, "Błąd", f"Nie znaleziono obiektu '{object_name}'.")
            return

        referencing_info = []
        obj_to_delete_instance = self.objects[object_name]

        for other_name, other_instance in self.objects.items():
            if other_name == object_name: continue

            try:
                other_class_name = other_instance.__class__.__name__
                if other_class_name in self.classes:
                    fields_info = self._get_all_fields_recursive(other_class_name)
                    for field_info in fields_info:
                        field = field_info['field']
                        field_type_str = field['type']

                        can_hold_reference = False
                        base_type = field_type_str.split('.')[-1].split('[')[0]

                        if base_type in self.classes:
                            can_hold_reference = True
                        elif ('Optional' in field_type_str or ('Union' in field_type_str and \
                                                               (
                                                                       'None' in field_type_str or 'NoneType' in field_type_str))) and \
                                '[' in field_type_str:
                            try:
                                content = field_type_str[field_type_str.rfind('[') + 1:field_type_str.rfind(']')]
                                parts = content.split(',')
                                can_hold_reference = any(
                                    part.strip().split('.')[-1].strip("'\" ") in self.classes
                                    for part in parts if part.strip().lower() not in ['none', 'nonetype']
                                )
                            except Exception:
                                can_hold_reference = False

                        if can_hold_reference:
                            try:
                                ref_value = getattr(other_instance, field['name'])
                                if ref_value is obj_to_delete_instance:
                                    referencing_info.append(f"{other_name}.{field['name']}")
                            except AttributeError:
                                pass
                            except Exception as e_get:
                                print(
                                    f"Error getting attribute {other_name}.{field['name']} for ref check: {e_get}")

            except Exception as e_outer:
                print(f"Error inspecting object {other_name} for references: {e_outer}")

        message = f"Czy na pewno chcesz usunąć obiekt '{object_name}'?"
        if referencing_info:
            message += "\n\nUWAGA: Referencje do tego obiektu istnieją w:\n- "
            message += "\n- ".join(referencing_info)
            message += "\n\nUsunięcie spowoduje, że te referencje zostaną ustawione na None."

        reply = QMessageBox.warning(
            self, "Potwierdzenie Usunięcia", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                for ref_str in referencing_info:
                    try:
                        ref_obj_name, ref_attr_name = ref_str.split('.', 1)
                        if ref_obj_name in self.objects:
                            print(f"Setting {ref_obj_name}.{ref_attr_name} to None (was {object_name})")
                            setattr(self.objects[ref_obj_name], ref_attr_name, None)
                            if ref_obj_name in self.object_data and 'attributes' in self.object_data[ref_obj_name]:
                                if ref_attr_name in self.object_data[ref_obj_name]['attributes']:
                                    self.object_data[ref_obj_name]['attributes'][ref_attr_name] = None
                    except Exception as e_set:
                        print(
                            f"Error setting reference to None in {ref_str}: {e_set}")

                del self.objects[object_name]
                if object_name in self.object_data:
                    del self.object_data[object_name]

                self.objects_changed.emit()
                QMessageBox.information(self, "Sukces", f"Obiekt '{object_name}' został usunięty.")

                if self.object_name_input.text() == object_name:
                    self.object_name_input.clear()
                    class_name_deleted = self.object_data.get(object_name, {}).get(
                        'class')
                    if class_name_deleted:
                        index = self.object_class_combo.findText(class_name_deleted)
                        if index >= 0:
                            self.object_class_combo.setCurrentIndex(-1)
                    else:
                        self.object_class_combo.setCurrentIndex(-1)
                    self._update_object_creation_form()


            except KeyError:
                QMessageBox.critical(self, "Błąd",
                                     f"Nie udało się usunąć obiektu '{object_name}' (KeyError - już usunięty?).")
            except Exception as e:
                QMessageBox.critical(self, "Błąd",
                                     f"Wystąpił nieoczekiwany błąd podczas usuwania '{object_name}': {e}")

    def _save_objects_to_mongodb(self):
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
            return

        try:
            try:
                from MongoDB.main import PyMongoConverter
            except ImportError:
                try:
                    from main import PyMongoConverter
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'PyMongoConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. MongoDB/main.py lub main.py) istnieje.")
                    return
            import pymongo

            connection_string = "mongodb://localhost:27017/"
            db_name = "object_generator_db"

            converter = None
            try:
                print(f"Connecting to MongoDB: {connection_string}, DB: {db_name}")
                converter = PyMongoConverter(connection_string=connection_string, db_name=db_name)
                converter.client.admin.command('ping')
                print("MongoDB connection successful.")

                saved_count = 0
                errors = []
                for obj_name, obj in self.objects.items():
                    print(f"Saving {obj_name} ({obj.__class__.__name__})...")
                    try:
                        converter.save_to_mongodb(obj)
                        saved_count += 1
                    except Exception as e:
                        error_msg = f"Failed saving '{obj_name}': {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)

                if not errors:
                    QMessageBox.information(self, "Sukces",
                                            f"Zapisano {saved_count} obiektów do MongoDB (Baza: {db_name}).")
                else:
                    QMessageBox.warning(self, "Błędy Zapisu",
                                        f"Zapisano {saved_count}/{len(self.objects)} obiektów.\n\nBłędy:\n" + "\n".join(
                                            errors))

            except pymongo.errors.ConnectionFailure as e:
                QMessageBox.critical(self, "Błąd Połączenia MongoDB", f"Nie można połączyć z MongoDB.\n{e}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd Zapisu MongoDB", f"Wystąpił błąd: {str(e)}")
            finally:
                if converter: converter.close()

        except ImportError:
            QMessageBox.critical(self, "Brak Biblioteki",
                                 "Biblioteka 'pymongo' nie jest zainstalowana (`pip install pymongo`).")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nieoczekiwany błąd: {e}")

    def _save_objects_to_cassandra(self):
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
            return

        try:
            try:
                from Cassandra.main import PyCassandraConverter
            except ImportError:
                try:
                    from main import PyCassandraConverter
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'PyCassandraConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. Cassandra/main.py lub main.py) istnieje.")
                    return

            from cassandra.cluster import NoHostAvailable

            keyspace = "object_db"

            converter = None
            try:
                print(f"Initializing Cassandra connection for keyspace: {keyspace}")
                converter = PyCassandraConverter(keyspace=keyspace)

                print("PyCassandraConverter initialized.")

                saved_count = 0
                errors = []
                for obj_name, obj in self.objects.items():
                    print(f"Saving {obj_name} ({obj.__class__.__name__}) to Cassandra...")
                    try:
                        converter.save_to_cassandra(obj)
                        saved_count += 1
                    except Exception as e:
                        error_msg = f"Failed saving '{obj_name}' to Cassandra: {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)

                if not errors:
                    QMessageBox.information(self, "Sukces",
                                            f"Zapisano {saved_count} obiektów do Cassandra (Keyspace: {keyspace}).")
                else:
                    QMessageBox.warning(self, "Błędy Zapisu",
                                        f"Zapisano {saved_count}/{len(self.objects)} obiektów do Cassandra.\n\nBłędy:\n" + "\n".join(
                                            errors))

            except NoHostAvailable as e:
                QMessageBox.critical(self, "Błąd Połączenia Cassandra",
                                     f"Nie można połączyć z klastrem Cassandra dla keyspace '{keyspace}'.\nSprawdź ustawienia i dostępność bazy.\n{e}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd Zapisu Cassandra", f"Wystąpił nieoczekiwany błąd: {str(e)}")
            finally:
                if converter:
                    try:
                        print("Closing Cassandra connection...")
                        converter.close()
                        print("Cassandra connection closed.")
                    except Exception as e:
                        print(f"Error closing Cassandra connection: {e}")


        except ImportError:
            QMessageBox.critical(self, "Brak Biblioteki",
                                 "Biblioteka 'cassandra-driver' nie jest zainstalowana.\n"
                                 "Zainstaluj ją używając: pip install cassandra-driver")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nieoczekiwany błąd: {e}")

    def _save_objects_to_neo4j(self):
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do zapisania.")
            return

        try:
            try:
                from Neo4j.main import Neo4jConverter
            except ImportError:
                try:
                    from main import Neo4jConverter
                except ImportError:
                    QMessageBox.critical(self, "Błąd Importu",
                                         "Nie znaleziono klasy 'Neo4jConverter'.\n"
                                         "Upewnij się, że plik z konwerterem (np. Neo4j/main.py lub main.py) istnieje.")
                    return

            uri = "bolt://localhost:7687"
            user = "neo4j"
            password = "password"

            converter = None
            try:
                print(f"Connecting to Neo4j at {uri} as user '{user}'")
                converter = Neo4jConverter(uri=uri, user=user, password=password)

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
        referenced_objects = set()

        for obj_name, obj_instance in self.objects.items():
            class_name = obj_instance.__class__.__name__
            if class_name not in self.classes:
                continue

            fields_info = self._get_all_fields_recursive(class_name)
            for field_info in fields_info:
                field = field_info['field']
                field_type = field['type']

                if self._is_object_reference_type(field_type):
                    try:
                        referenced_obj = getattr(obj_instance, field['name'])
                        if referenced_obj is not None:
                            for ref_name, ref_instance in self.objects.items():
                                if ref_instance is referenced_obj:
                                    referenced_objects.add(ref_name)
                                    break
                    except AttributeError:
                        pass

        top_level = [name for name in self.objects.keys() if name not in referenced_objects]
        return top_level

    def _is_object_reference_type(self, type_str: str) -> bool:
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

    def _get_object_attribute_safely(self, obj_instance, attr_name):
        try:
            return getattr(obj_instance, attr_name)
        except AttributeError:
            for actual_attr_name in dir(obj_instance):
                if actual_attr_name.startswith('_'):
                    continue
                try:
                    actual_attr_value = getattr(obj_instance, actual_attr_name)
                    if hasattr(actual_attr_value, attr_name.split('_')[-1]):
                        return getattr(actual_attr_value, attr_name.split('_')[-1])
                except:
                    continue
            return None

    def _update_object_tree(self):
        self.object_tree.clear()
        sorted_object_names = sorted(self.objects.keys())

        for obj_name in sorted_object_names:
            obj_instance = self.objects.get(obj_name)
            if obj_instance is None:
                continue

            obj_item = QTreeWidgetItem([obj_name])
            font = obj_item.font(0)
            font.setBold(True)
            obj_item.setFont(0, font)
            self.object_tree.addTopLevelItem(obj_item)

            class_item = QTreeWidgetItem(["Klasa", obj_instance.__class__.__name__])
            obj_item.addChild(class_item)

            attrs_item = QTreeWidgetItem(["Atrybuty"])
            obj_item.addChild(attrs_item)

            all_attrs = self._get_all_attributes(obj_instance.__class__.__name__)

            for attr_name, attr_type in sorted(all_attrs.items()):
                try:
                    attr_value = getattr(obj_instance, attr_name)
                    display_value = self._format_attribute_value(attr_value)
                    attr_item = QTreeWidgetItem([attr_name, display_value])
                    attrs_item.addChild(attr_item)
                except Exception as e:
                    error_item = QTreeWidgetItem([attr_name, f"<Błąd: {str(e)}>"])
                    attrs_item.addChild(error_item)

            obj_item.setExpanded(True)
            attrs_item.setExpanded(True)

    def _format_attribute_value(self, value):
        if value is None:
            return "None"

        if isinstance(value, (list, tuple, set, frozenset)):
            items = []
            for item in value:
                if any(item is obj for obj in self.objects.values()):
                    obj_name = next((name for name, obj in self.objects.items() if obj is item), None)
                    items.append(f"-> {obj_name}" if obj_name else f"<{item.__class__.__name__}>")
                else:
                    items.append(str(item))

            if isinstance(value, tuple):
                return f"({', '.join(items)})"
            elif isinstance(value, set):
                return f"{{{', '.join(items)}}}"
            elif isinstance(value, frozenset):
                return f"frozenset({{{', '.join(items)}}})"
            else:
                return f"[{', '.join(items)}]"

        elif isinstance(value, dict):
            pairs = []
            for k, v in value.items():
                key_str = f'"{k}"' if isinstance(k, str) else str(k)
                if any(v is obj for obj in self.objects.values()):
                    obj_name = next((name for name, obj in self.objects.items() if obj is v), None)
                    val_str = f"-> {obj_name}" if obj_name else f"<{v.__class__.__name__}>"
                else:
                    val_str = str(v)
                pairs.append(f"{key_str}: {val_str}")
            return f"{{{', '.join(pairs)}}}"

        elif any(value is obj for obj in self.objects.values()):
            obj_name = next((name for name, obj in self.objects.items() if obj is value), None)
            return f"-> {obj_name}" if obj_name else f"<{value.__class__.__name__}>"

        return str(value)

    def _get_all_attributes(self, class_name):
        attributes = {}

        if class_name not in self.classes:
            return attributes

        parent_class = self.classes[class_name].get('inherits')
        if parent_class:
            attributes.update(self._get_all_attributes(parent_class))

        for field in self.classes[class_name].get('fields', []):
            attributes[field['name']] = field['type']

        return attributes

    def _format_collection_display(self, collection_value, collection_type):
        if not collection_value:
            if collection_type == 'list':
                return "[]"
            elif collection_type == 'tuple':
                return "[]"
            elif collection_type == 'set':
                return "set()" if isinstance(collection_value, set) else "frozenset()"
            elif collection_type == 'dict':
                return "{}"
            else:
                return str(collection_value)

        if collection_type == 'dict':
            return self._format_dict_display(collection_value)

        formatted_items = []

        for item in collection_value:
            found_name = None
            for obj_name, obj_instance in self.objects.items():
                if obj_instance is item:
                    found_name = obj_name
                    break

            if found_name:
                formatted_items.append(f"->{found_name}")
            else:
                if isinstance(item, str):
                    formatted_items.append(f'"{item}"')
                else:
                    formatted_items.append(str(item))

        if collection_type != 'tuple':
            formatted_items.sort()

        items_str = ", ".join(formatted_items)

        if collection_type == 'list' or collection_type == 'tuple':
            return f"[{items_str}]"
        elif collection_type == 'set':
            if isinstance(collection_value, frozenset):
                return f"frozenset({{{items_str}}})"
            else:
                return f"{{{items_str}}}"

        return str(collection_value)

    def _format_dict_display(self, dict_value):
        if not dict_value:
            return "{}"

        formatted_pairs = []

        for key, value in dict_value.items():
            if isinstance(key, str):
                formatted_key = f'"{key}"'
            else:
                formatted_key = str(key)

            found_name = None
            if hasattr(value, '__class__'):
                for obj_name, obj_instance in self.objects.items():
                    if obj_instance is value:
                        found_name = obj_name
                        break

            if found_name:
                formatted_value = f"->{found_name}"
            elif isinstance(value, str):
                formatted_value = f'"{value}"'
            elif isinstance(value, (list, tuple, set, frozenset)):
                if isinstance(value, list):
                    formatted_value = self._format_collection_display(value, 'list')
                elif isinstance(value, tuple):
                    formatted_value = self._format_collection_display(value, 'tuple')
                elif isinstance(value, set):
                    formatted_value = self._format_collection_display(value, 'set')
                elif isinstance(value, frozenset):
                    formatted_value = self._format_collection_display(value, 'set')
            elif isinstance(value, dict):
                if len(str(value)) > 50:
                    formatted_value = f"{{...{len(value)} items...}}"
                else:
                    formatted_value = self._format_dict_display(value)
            else:
                value_str = str(value)
                if hasattr(value, '__class__') and hasattr(value.__class__, '__name__'):
                    class_name = value.__class__.__name__
                    if any(obj_instance is value for obj_instance in self.objects.values()):
                        formatted_value = f"<{class_name}>"
                    else:
                        formatted_value = str(value)
                else:
                    formatted_value = value_str

            formatted_pairs.append(f"{formatted_key}: {formatted_value}")

        formatted_pairs.sort()

        if len(formatted_pairs) > 5:
            displayed_pairs = formatted_pairs[:3]
            remaining_count = len(formatted_pairs) - 3
            pairs_str = ", ".join(displayed_pairs) + f", ...+{remaining_count} more"
        else:
            pairs_str = ", ".join(formatted_pairs)

        return f"{{{pairs_str}}}"

    def _update_composition_combos(self):
        for i in range(self.object_fields_layout.rowCount()):
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not field_item: continue
            field_widget = field_item.widget()

            if isinstance(field_widget, QComboBox):
                label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                expected_base_type = None
                if label_item and isinstance(label_item.widget(), QLabel):
                    label_text = label_item.widget().text()
                    try:
                        type_part = label_text.split('(')[1].split(')')[0]
                        base_type_str = type_part.split('[')[0].strip()
                        if base_type_str in self.classes:
                            expected_base_type = base_type_str
                        elif '[' in type_part:
                            content = type_part[type_part.find('[') + 1:type_part.rfind(']')]
                            parts = [p.strip() for p in content.split(',')]
                            for part in parts:
                                if part.lower() != 'none' and part.lower() != 'nonetype':
                                    potential_name = part.split('.')[-1].strip("'\" ")
                                    if potential_name in self.classes:
                                        expected_base_type = potential_name;
                                        break
                    except Exception:
                        pass

                if not expected_base_type: continue

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

    def _show_connect_objects_dialog(self):
        if not self.objects:
            QMessageBox.information(self, "Informacja", "Brak obiektów do połączenia.")
            return

        dialog = ConnectObjectsDialog(self.objects, self.classes, self)
        if dialog.exec():
            connection_details = dialog.get_connection_details()
            if connection_details:
                target_name, attr_name, source_data, container_type = connection_details
                self._perform_object_connection(target_name, attr_name, source_data, container_type)

    def _perform_object_connection(self, target_obj_name: str, attribute_name: str, source_obj_data: Any,
                                   container_type: str):
        try:
            if target_obj_name not in self.objects:
                QMessageBox.critical(self, "Błąd", f"Obiekt docelowy '{target_obj_name}' nie istnieje")
                return

            target_obj = self.objects[target_obj_name]

            if container_type == 'frozenset':
                valid_sources = []
                already_in_set = set()
                if hasattr(target_obj, attribute_name):
                    current_frozenset = getattr(target_obj, attribute_name)
                    if isinstance(current_frozenset, frozenset):
                        already_in_set = set(current_frozenset)

                if not isinstance(source_obj_data, list):
                    source_obj_data = [source_obj_data]

                duplicates = []
                for src_name in source_obj_data:
                    if src_name in self.objects:
                        obj = self.objects[src_name]
                        if obj in already_in_set or obj in valid_sources:
                            duplicates.append(src_name)
                        else:
                            valid_sources.append(obj)

                new_frozenset = frozenset(list(already_in_set) + valid_sources)
                setattr(target_obj, attribute_name, new_frozenset)

                actual_connected_names = [src for src in source_obj_data if
                                          src in self.objects and src not in duplicates]
                connection_message_suffix = f"-> frozenset({{{', '.join(actual_connected_names)}}})"

                if duplicates:
                    QMessageBox.information(self, "Uwaga", f"Pominięto duplikaty: {', '.join(duplicates)}")

            elif container_type == 'tuple':
                valid_sources = []
                already_in_tuple = []
                if hasattr(target_obj, attribute_name):
                    current_tuple = getattr(target_obj, attribute_name)
                    if isinstance(current_tuple, tuple):
                        already_in_tuple = list(current_tuple)

                if not isinstance(source_obj_data, list):
                    source_obj_data = [source_obj_data]

                for src_name in source_obj_data:
                    if src_name in self.objects:
                        obj = self.objects[src_name]
                        valid_sources.append(obj)

                new_tuple = tuple(already_in_tuple + valid_sources)
                setattr(target_obj, attribute_name, new_tuple)

                actual_connected_names = [src for src in source_obj_data if src in self.objects]
                connection_message_suffix = f"-> ({', '.join(actual_connected_names)})"

            elif container_type == 'set':
                valid_sources = []
                already_in_set = set()
                if hasattr(target_obj, attribute_name):
                    already_in_set = getattr(target_obj, attribute_name)
                    if not isinstance(already_in_set, set):
                        already_in_set = set()
                if not isinstance(source_obj_data, list):
                    source_obj_data = [source_obj_data]

                duplicates = []
                for src_name in source_obj_data:
                    if src_name in self.objects:
                        obj = self.objects[src_name]
                        if obj in already_in_set or obj in valid_sources:
                            duplicates.append(src_name)
                        else:
                            valid_sources.append(obj)
                new_set = set(already_in_set)
                new_set.update(valid_sources)
                setattr(target_obj, attribute_name, new_set)

                actual_connected_names = [src for src in source_obj_data if
                                          src in self.objects and src not in duplicates]
                connection_message_suffix = f"-> {{{', '.join(actual_connected_names)}}}"
                if duplicates:
                    QMessageBox.information(self, "Uwaga", f"Pominięto duplikaty: {', '.join(duplicates)}")

            elif container_type == 'list':
                valid_sources = []
                already_in_list = []
                if hasattr(target_obj, attribute_name):
                    already_in_list = getattr(target_obj, attribute_name)
                    if not isinstance(already_in_list, list):
                        already_in_list = []
                if not isinstance(source_obj_data, list):
                    source_obj_data = [source_obj_data]

                for src_name in source_obj_data:
                    if src_name in self.objects:
                        obj = self.objects[src_name]
                        if obj not in already_in_list:
                            valid_sources.append(obj)
                new_list = list(already_in_list) + valid_sources
                setattr(target_obj, attribute_name, new_list)
                actual_connected_names = [src for src in source_obj_data if src in self.objects]
                connection_message_suffix = f"-> [{', '.join(actual_connected_names)}]"

            elif container_type == 'dict':
                current_dict = {}
                if hasattr(target_obj, attribute_name):
                    current_dict = getattr(target_obj, attribute_name)
                    if not isinstance(current_dict, dict):
                        current_dict = {}

                new_dict = dict(current_dict)

                if isinstance(source_obj_data, dict):
                    added_items = []
                    for key, obj_name in source_obj_data.items():
                        if obj_name in self.objects:
                            new_dict[key] = self.objects[obj_name]
                            added_items.append(f"{key}: {obj_name}")

                    setattr(target_obj, attribute_name, new_dict)
                    connection_message_suffix = f"-> {{{', '.join(added_items)}}}"

                elif isinstance(source_obj_data, list):
                    for i, obj_name in enumerate(source_obj_data):
                        if obj_name in self.objects:
                            key = f"key_{len(new_dict) + i}"
                            new_dict[key] = self.objects[obj_name]

                    setattr(target_obj, attribute_name, new_dict)
                    connection_message_suffix = f"-> Dict z {len(source_obj_data)} elementami"
                else:
                    connection_message_suffix = "-> Błędny format słownika"

            else:
                if isinstance(source_obj_data, str) and source_obj_data in self.objects:
                    setattr(target_obj, attribute_name, self.objects[source_obj_data])
                    connection_message_suffix = f"-> {source_obj_data}"
                else:
                    QMessageBox.warning(self, "Błąd", f"Nieznany typ kontenera: {container_type}")
                    return

            if target_obj_name in self.object_data:
                if 'attributes' not in self.object_data[target_obj_name]:
                    self.object_data[target_obj_name]['attributes'] = {}
                self.object_data[target_obj_name]['attributes'][attribute_name] = getattr(target_obj, attribute_name)

            self.object_tree.blockSignals(True)
            try:
                self.objects_changed.emit()
            finally:
                self.object_tree.blockSignals(False)

            QMessageBox.information(self, "Sukces",
                                    f"Połączono: {target_obj_name}.{attribute_name} {connection_message_suffix}")

        except Exception as e:
            QMessageBox.critical(self, "Błąd krytyczny", f"Wystąpił błąd: {str(e)}")
            import traceback
            traceback.print_exc()


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
        _temp_app = QApplication.instance()
        if _temp_app is None:
            _temp_app = QApplication(sys.argv)
        QMessageBox.critical(None, "Błąd Importu Modułu", msg)
        from types import ModuleType

        classes_module = ModuleType(CLASSES_MODULE_NAME)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = ObjectGeneratorApp(classes_module)
    window.show()

    sys.exit(app.exec())

