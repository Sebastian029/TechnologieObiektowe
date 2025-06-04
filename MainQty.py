import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFormLayout, QScrollArea, QFileDialog, QCheckBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Dict, List, Optional, Any, Tuple

ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]


class ClassDiagramEditor(QMainWindow):
    classes_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Edytor Diagramów Klas i Obiektów")
        self.setGeometry(100, 100, 1100, 750)
        self.classes: ClassesDict = {}
        self.selected_class_editor: Optional[str] = None
        self.mode_switch_button = None
        self._switch_mode = None
        self._setup_main_ui()
        self._update_all_class_editor_views()

    def _validate_class_name(self, class_name: str) -> Tuple[bool, str]:
        if not class_name:
            return False, "Nazwa klasy nie może być pusta!"
        if not class_name[0].isupper():
            return False, "Nazwa klasy musi zaczynać się wielką literą!"
        if ' ' in class_name or not class_name.isidentifier():
            return False, "Nazwa klasy zawiera niedozwolone znaki lub jest słowem kluczowym Pythona."
        if class_name in self.classes:
            return False, "Klasa o tej nazwie już istnieje!"
        return True, ""

    def _validate_field_name(self, field_name: str) -> Tuple[bool, str]:
        if not field_name:
            return False, "Nazwa pola nie może być pusta."
        if not field_name[0].islower():
            return False, "Nazwa pola musi zaczynać się małą literą."
        if ' ' in field_name or not field_name.isidentifier():
            return False, "Nazwa pola zawiera niedozwolone znaki lub jest słowem kluczowym."
        return True, ""

    def _show_message(self, message_type: str, title: str, message: str,
                      buttons=None) -> bool:
        if message_type == "warning":
            QMessageBox.warning(self, title, message)
            return False
        elif message_type == "error":
            QMessageBox.critical(self, title, message)
            return False
        elif message_type == "info":
            QMessageBox.information(self, title, message)
            return True
        elif message_type == "question":
            reply = QMessageBox.question(self, title, message, buttons or
                                         (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No),
                                         QMessageBox.StandardButton.No)
            return reply == QMessageBox.StandardButton.Yes

    def _setup_combo_box(self, combo_box: QComboBox, items: List[str],
                         default_selection: str = None):
        current_selection = combo_box.currentText() if default_selection is None else default_selection
        combo_box.clear()
        combo_box.addItems(items)

        index = combo_box.findText(current_selection)
        if index != -1:
            combo_box.setCurrentIndex(index)
        elif combo_box.count() > 0:
            combo_box.setCurrentIndex(0)

    def _setup_list_widget(self, list_widget: QListWidget, items: List[str],
                           current_selection: str = None):
        list_widget.clear()
        list_widget.addItems(items)

        if current_selection:
            items_found = list_widget.findItems(current_selection, Qt.MatchFlag.MatchExactly)
            if items_found:
                list_widget.setCurrentItem(items_found[0])

    def _create_container_type(self, base_type: str, container_type: str) -> str:
        container_mapping = {
            "List": f"List[{base_type}]",
            "Dict": f"Dict[str, {base_type}]",
            "Tuple": f"Tuple[{base_type}, ...]",
            "FrozenSet": f"FrozenSet[{base_type}]",
            "Set": f"Set[{base_type}]"
        }
        return container_mapping.get(container_type, base_type)

    def _check_inheritance_path(self, start_class: str, target_class: str,
                                check_type: str = "cycle") -> bool:
        current = target_class
        visited = set()

        while current in self.classes:
            if current == start_class:
                return True
            if current in visited:
                return False
            visited.add(current)
            current = self.classes[current].get('inherits')

        return False

    def _setup_main_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        self.generate_code_button = QPushButton("Generuj kod")
        self.generate_code_button.clicked.connect(self._save_python_code)
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(self.generate_code_button)
        top_bar_layout.addStretch()
        main_layout.addLayout(top_bar_layout)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)
        self.class_editor_widget = self._create_class_editor_widget()
        self.stacked_widget.addWidget(self.class_editor_widget)

    def _get_type_hint_str(self, type_str: str, is_optional: bool) -> str:
        container_parsers = {
            "Dict[": lambda t: self._parse_dict_type(t),
            "List[": lambda t: f"List[{t[5:-1]}]",
            "Tuple[": lambda t: f"Tuple[{t[6:-1]}]",
            "FrozenSet[": lambda t: f"FrozenSet[{t[10:-1]}]",
            "Set[": lambda t: f"Set[{t[4:-1]}]"
        }

        container_hint = None
        for prefix, parser in container_parsers.items():
            if type_str.startswith(prefix):
                container_hint = parser(type_str)
                break

        if container_hint is None:
            is_class_type = type_str in self.classes
            container_hint = f"'{type_str}'" if is_class_type else type_str

        return f"Optional[{container_hint}]" if is_optional else container_hint

    def _parse_dict_type(self, type_str: str) -> str:
        inner_types = type_str[5:-1].split(",")
        if len(inner_types) == 2:
            key_type, value_type = inner_types[0].strip(), inner_types[1].strip()
            base_hint = f"{key_type}, {value_type}"
        else:
            value_type = type_str[5:-1].strip()
            base_hint = f"str, {value_type}"
        return f"Dict[{base_hint}]"

    def _generate_python_code(self) -> str:
        if not self.classes:
            return ""

        code_lines = self._generate_imports()

        sorted_classes = self._sort_classes_by_inheritance()

        for class_name in sorted_classes:
            class_code = self._generate_class_code(class_name)
            code_lines.extend(class_code)

        return "\n".join(code_lines)

    def _generate_imports(self) -> List[str]:
        return [
            "from __future__ import annotations",
            "from typing import Dict, List, Optional, Set, Tuple, FrozenSet"
        ]

    def _generate_class_code(self, class_name: str) -> List[str]:
        class_data = self.classes[class_name]
        code_lines = []

        code_lines.extend(self._generate_class_definition(class_name, class_data))
        code_lines.extend(self._generate_init_method(class_name, class_data))

        if class_data.get('auto_eq_hash'):
            code_lines.extend(self._generate_eq_hash_methods(class_name, class_data.get('fields', [])))

        code_lines.extend(self._generate_composition_methods(class_name, class_data))

        return code_lines

    def _generate_class_definition(self, class_name: str, class_data: Dict[str, Any]) -> List[str]:
        parent_name = class_data.get('inherits')
        parent_str = f"({parent_name})" if parent_name else ""
        return [f"\nclass {class_name}{parent_str}:"]

    def _generate_eq_hash_methods(self, class_name: str, fields: List[Dict[str, str]]) -> List[str]:
        fields_for_eq_hash = [
            field['name'] for field in fields
            if not self._is_container_type(field['type'])
        ]

        if not fields_for_eq_hash:
            return []

        code_lines = ["", "    def __eq__(self, other):"]
        code_lines.append(f"        if not isinstance(other, {class_name}):")
        code_lines.append("            return NotImplemented")

        tuple_self = ", ".join([f"self.{f}" for f in fields_for_eq_hash])
        tuple_other = ", ".join([f"other.{f}" for f in fields_for_eq_hash])
        code_lines.append(f"        return ({tuple_self},) == ({tuple_other},)")

        code_lines.extend(["", "    def __hash__(self):", f"        return hash(({tuple_self},))"])
        return code_lines

    def _generate_init_method(self, class_name: str, class_data: Dict[str, Any]) -> List[str]:
        fields = class_data.get('fields', [])
        parent_name = class_data.get('inherits')
        compositions = class_data.get('compositions', [])

        init_params = ['self']
        assignments = []

        all_inherited_fields = self._get_all_inherited_fields_ordered(class_name)

        for field in all_inherited_fields:
            if not self._is_composition_field_type(field['type'], compositions):
                type_hint = self._get_type_hint_str(field['type'], False)
                init_params.append(f"{field['name']}: {type_hint}")

        for field in fields:
            if not self._is_composition_field_type(field['type'], compositions):
                type_hint = self._get_type_hint_str(field['type'], False)
                if self._is_container_type(field['type']):
                    init_params.append(f"{field['name']}: {type_hint} = None")
                    default_value = self._get_default_container_value(field['type'])
                    assignments.append(
                        f"        self.{field['name']} = {field['name']} if {field['name']} is not None else {default_value}")
                else:
                    init_params.append(f"{field['name']}: {type_hint}")
                    assignments.append(f"        self.{field['name']}: {type_hint} = {field['name']}")

        for field in fields:
            if self._is_composition_field_type(field['type'], compositions):
                field_type = self._extract_base_type(field['type'])
                if field_type in self.classes and not field['type'].startswith('List['):
                    composition_class_data = self.classes[field_type]
                    composition_fields = composition_class_data.get('fields', [])
                    composition_compositions = composition_class_data.get('compositions', [])
                    for comp_field in composition_fields:
                        if not self._is_composition_field_type(comp_field['type'], composition_compositions):
                            param_name = f"{field['name']}_{comp_field['name']}"
                            type_hint = self._get_type_hint_str(comp_field['type'], False)
                            init_params.append(f"{param_name}: {type_hint}")

        if not init_params[1:] and not fields and not parent_name:
            return ["    pass"]

        code_lines = [f"    def __init__({', '.join(init_params)}):"]

        if parent_name:
            parent_params = []
            for field in all_inherited_fields:
                if not self._is_composition_field_type(field['type'], compositions):
                    parent_params.append(field['name'])

            if parent_params:
                code_lines.append(f"        super().__init__({', '.join(parent_params)})")
            else:
                code_lines.append("        super().__init__()")

        if assignments:
            code_lines.extend(assignments)

        composition_assignments = self._generate_composition_assignments(fields, compositions)
        if composition_assignments:
            code_lines.extend(composition_assignments)

        if not assignments and not composition_assignments and not parent_name:
            code_lines.append("        pass")

        return code_lines

    def _get_all_inherited_fields_ordered(self, class_name: str) -> List[Dict[str, str]]:
        if class_name not in self.classes:
            return []

        parent_name = self.classes[class_name].get('inherits')
        if not parent_name or parent_name not in self.classes:
            return []

        inherited_fields = self._get_all_inherited_fields_ordered(parent_name)

        parent_fields = self.classes[parent_name].get('fields', [])

        existing_names = {field['name'] for field in inherited_fields}
        for field in parent_fields:
            if field['name'] not in existing_names:
                inherited_fields.append(field)

        return inherited_fields

    def _generate_composition_assignments(self, fields: List[Dict[str, str]],
                                          compositions: List[str]) -> List[str]:
        assignments = []

        for field in fields:
            if self._is_composition_field_type(field['type'], compositions):
                field_type = self._extract_base_type(field['type'])
                if field['type'].startswith('List['):
                    assignments.append(f"        self.{field['name']}: List[{field_type}] = []")
                else:
                    if field_type in self.classes:
                        composition_class_data = self.classes[field_type]
                        composition_fields = composition_class_data.get('fields', [])
                        composition_compositions = composition_class_data.get('compositions', [])
                        comp_params = []
                        for comp_field in composition_fields:
                            if not self._is_composition_field_type(comp_field['type'], composition_compositions):
                                param_name = f"{field['name']}_{comp_field['name']}"
                                comp_params.append(param_name)
                        params_str = ', '.join(comp_params) if comp_params else ""
                        assignments.append(
                            f"        self.{field['name']}: {field_type} = {field_type}({params_str})")
                    else:
                        assignments.append(
                            f"        self.{field['name']}: {field_type} = {field_type}()")

        return assignments

    def _generate_composition_methods(self, class_name: str, class_data: Dict[str, Any]) -> List[str]:
        fields = class_data.get('fields', [])
        compositions = class_data.get('compositions', [])
        methods = []

        for field in fields:
            if self._is_composition_field_type(field['type'], compositions):
                field_type = self._extract_base_type(field['type'])
                if field['type'].startswith('List['):
                    method_code = self._generate_add_method(field, field_type)
                    methods.extend(method_code)

        return methods

    def _generate_add_method(self, field: Dict[str, str], field_type: str) -> List[str]:
        method_name = f"add_{field['name'][:-1] if field['name'].endswith('s') else field['name']}"

        if field_type in self.classes:
            composition_class_data = self.classes[field_type]
            composition_fields = composition_class_data.get('fields', [])
            composition_compositions = composition_class_data.get('compositions', [])
            method_params = ['self']
            comp_params = []

            for comp_field in composition_fields:
                if not self._is_composition_field_type(comp_field['type'], composition_compositions):
                    type_hint = self._get_type_hint_str(comp_field['type'], False)
                    method_params.append(f"{comp_field['name']}: {type_hint}")
                    comp_params.append(comp_field['name'])

            params_str = ', '.join(comp_params) if comp_params else ""
            return [
                f"\n    def {method_name}({', '.join(method_params)}) -> {field_type}:",
                f"        new_item = {field_type}({params_str})",
                f"        self.{field['name']}.append(new_item)",
                f"        return new_item"
            ]
        else:
            return [
                f"\n    def {method_name}(self) -> {field_type}:",
                f"        new_item = {field_type}()",
                f"        self.{field['name']}.append(new_item)",
                f"        return new_item"
            ]

    def _is_container_type(self, field_type: str) -> bool:
        container_types = ['List[', 'Set[', 'FrozenSet[', 'Dict[', 'Tuple[']
        return any(field_type.startswith(container) for container in container_types)

    def _get_default_container_value(self, field_type: str) -> str:
        defaults = {
            'List[': "[]",
            'Set[': "set()",
            'FrozenSet[': "frozenset()",
            'Dict[': "{}",
            'Tuple[': "tuple()"
        }

        for prefix, default in defaults.items():
            if field_type.startswith(prefix):
                return default
        return "None"

    def _is_composition_field_type(self, field_type: str, compositions: List[str]) -> bool:
        base_type = self._extract_base_type(field_type)
        return base_type in compositions

    def _extract_base_type(self, field_type: str) -> str:
        extractors = {
            'List[': lambda t: t[5:-1],
            'Set[': lambda t: t[4:-1],
            'FrozenSet[': lambda t: t[10:-1],
            'Tuple[': lambda t: t[6:-1].split(',')[0].strip(),
            'Dict[': lambda t: t[5:-1].split(',')[1].strip() if len(t[5:-1].split(',')) == 2 else t
        }

        for prefix, extractor in extractors.items():
            if field_type.startswith(prefix):
                return extractor(field_type)
        return field_type

    def _get_parent_fields(self, class_name: str) -> List[Dict[str, str]]:
        parent_name = self.classes[class_name].get('inherits')
        if not parent_name or parent_name not in self.classes:
            return []
        return self.classes[parent_name].get('fields', [])

    def _sort_classes_by_inheritance(self) -> List[str]:
        class_order = []
        remaining_classes = set(self.classes.keys())
        processing = set()

        def add_class_to_order(cls_name):
            if cls_name in class_order or cls_name in processing:
                return
            processing.add(cls_name)
            parent_name = self.classes[cls_name].get('inherits')
            if parent_name and parent_name in self.classes:
                add_class_to_order(parent_name)
            processing.remove(cls_name)
            if cls_name not in class_order:
                class_order.append(cls_name)

        while remaining_classes:
            sorted_keys = sorted(list(remaining_classes))
            for cls in sorted_keys:
                if cls not in class_order:
                    add_class_to_order(cls)
            remaining_classes = set(self.classes.keys()) - set(class_order)
            if remaining_classes:
                class_order.extend(sorted(list(remaining_classes)))
                break

        return class_order

    def _save_python_code(self):
        if not self.classes:
            self._show_message("info", "Brak Klas", "Nie zdefiniowano żadnych klas do wygenerowania kodu.")
            return

        try:
            generated_code = self._generate_python_code()
        except Exception as e:
            self._show_message("error", "Błąd Generowania Kodu", f"Wystąpił błąd podczas generowania kodu:\n{e}")
            import traceback
            traceback.print_exc()
            return

        if not generated_code:
            self._show_message("info", "Brak kodu", "Generowanie nie zwróciło żadnego kodu.")
            return

        default_filename = "wygenerowany_kod.py"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz kod Pythona", default_filename, "Python Files (*.py);;All Files (*)")

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(generated_code)
                self._show_message("info", "Sukces", f"Kod Pythona został zapisany do:\n{file_path}")
            except IOError as e:
                self._show_message("error", "Błąd Zapisu", f"Nie można zapisać pliku:\n{e}")
            except Exception as e:
                self._show_message("error", "Błąd Zapisu", f"Wystąpił nieoczekiwany błąd podczas zapisu:\n{e}")

    def _create_class_editor_widget(self) -> QWidget:
        editor_widget = QWidget()
        editor_layout = QHBoxLayout(editor_widget)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(15, 15, 15, 15)
        side_layout.setSpacing(20)

        self.class_management_panel = self._create_class_management_panel()
        self.fields_management_panel = self._create_fields_management_panel()
        self.inheritance_management_panel = self._create_inheritance_management_panel()

        side_layout.addWidget(self.class_management_panel)
        side_layout.addWidget(self.fields_management_panel)
        side_layout.addWidget(self.inheritance_management_panel)
        side_layout.addStretch()
        side_panel.setLayout(side_layout)
        side_panel.setFixedWidth(370)

        self.class_tree = QTreeWidget()
        self.class_tree.setHeaderLabel("Struktura klas")
        self.class_tree.setMinimumWidth(400)

        editor_layout.addWidget(side_panel)
        editor_layout.addWidget(self.class_tree, 1)
        return editor_widget

    def _on_auto_eq_hash_checkbox_changed(self, state):
        if self.selected_class_editor:
            self.classes[self.selected_class_editor]['auto_eq_hash'] = self.editor_auto_eq_hash_checkbox.isChecked()

    def _create_class_management_panel(self) -> QWidget:
        group = QGroupBox("Zarządzanie klasami")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        form_layout = QFormLayout()
        self.editor_class_name_input = QLineEdit()
        self.editor_class_name_input.setPlaceholderText("Nazwa nowej klasy (Wielka litera)")
        form_layout.addRow("Nazwa klasy:", self.editor_class_name_input)
        layout.addLayout(form_layout)

        self.editor_add_class_btn = QPushButton("Dodaj klasę")
        layout.addWidget(self.editor_add_class_btn)

        layout.addWidget(QLabel("Istniejące klasy:"))
        self.editor_class_list = QListWidget()
        self.editor_class_list.setMinimumHeight(80)
        layout.addWidget(self.editor_class_list)

        btn_layout = QHBoxLayout()
        self.editor_delete_class_btn = QPushButton("Usuń zaznaczoną klasę")
        btn_layout.addStretch()
        btn_layout.addWidget(self.editor_delete_class_btn)
        layout.addLayout(btn_layout)

        self.editor_auto_eq_hash_checkbox = QCheckBox("Generuj __eq__ i __hash__ automatycznie")
        layout.addWidget(self.editor_auto_eq_hash_checkbox)

        self.editor_add_class_btn.clicked.connect(self.add_class)
        self.editor_class_list.itemClicked.connect(self.select_class_editor)
        self.editor_delete_class_btn.clicked.connect(self.delete_class)
        self.editor_auto_eq_hash_checkbox.stateChanged.connect(self._on_auto_eq_hash_checkbox_changed)
        return group

    def _create_fields_management_panel(self) -> QWidget:
        group = QGroupBox("Zarządzanie polami (dla wybranej klasy)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        form_layout = QFormLayout()
        self.editor_field_name_input = QLineEdit()
        self.editor_field_name_input.setPlaceholderText("Nazwa nowego pola (mała litera)")
        form_layout.addRow("Nazwa pola:", self.editor_field_name_input)

        self.editor_field_type_combo = QComboBox()
        self._update_editor_field_type_combo()
        self.editor_container_combo = QComboBox()
        self.editor_container_combo.addItem("Pojedyncza wartość", None)
        self.editor_container_combo.addItem("Lista", "List")
        self.editor_container_combo.addItem("Słownik", "Dict")
        self.editor_container_combo.addItem("Tuple", "Tuple")
        self.editor_container_combo.addItem("FrozenSet", "FrozenSet")
        self.editor_container_combo.addItem("Set", "Set")
        container_layout = QHBoxLayout()
        container_layout.addWidget(self.editor_field_type_combo, 1)
        container_layout.addWidget(self.editor_container_combo)
        form_layout.addRow("Typ pola:", container_layout)

        layout.addLayout(form_layout)

        self.editor_composition_checkbox = QCheckBox("Kompozycja")
        layout.addWidget(self.editor_composition_checkbox)

        btn_layout = QHBoxLayout()
        self.editor_add_field_btn = QPushButton("Dodaj pole")
        btn_layout.addStretch()
        btn_layout.addWidget(self.editor_add_field_btn)
        layout.addLayout(btn_layout)

        layout.addWidget(QLabel("Pola w klasie:"))
        self.editor_fields_list = QListWidget()
        self.editor_fields_list.setMinimumHeight(80)
        layout.addWidget(self.editor_fields_list)

        btn_layout2 = QHBoxLayout()
        self.editor_delete_field_btn = QPushButton("Usuń zaznaczone pole")
        btn_layout2.addStretch()
        btn_layout2.addWidget(self.editor_delete_field_btn)
        layout.addLayout(btn_layout2)

        self.editor_add_field_btn.clicked.connect(self.add_field)
        self.editor_delete_field_btn.clicked.connect(self.delete_field)
        group.setEnabled(False)
        return group

    def _update_editor_field_type_combo(self):
        basic_types = ["str", "int", "float", "bool", "complex"]
        class_names = sorted(self.classes.keys())

        all_items = basic_types.copy()
        if class_names:
            all_items.append("---")
            all_items.extend(class_names)

        self._setup_combo_box(self.editor_field_type_combo, all_items)

    def _create_inheritance_management_panel(self) -> QWidget:
        group = QGroupBox("Zarządzanie dziedziczeniem")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.editor_inheritance_target_combo = QComboBox()

        form_layout = QFormLayout()
        form_layout.addRow("Klasa nadrzędna:", self.editor_inheritance_target_combo)
        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        self.editor_add_inheritance_btn = QPushButton("Ustaw dziedziczenie")
        self.editor_delete_inheritance_btn = QPushButton("Usuń dziedziczenie")
        btn_layout.addWidget(self.editor_add_inheritance_btn)
        btn_layout.addWidget(self.editor_delete_inheritance_btn)
        layout.addLayout(btn_layout)

        self.editor_add_inheritance_btn.clicked.connect(self.add_relation)
        self.editor_delete_inheritance_btn.clicked.connect(self.delete_relation)
        group.setEnabled(False)
        return group

    def add_class(self):
        class_name = self.editor_class_name_input.text().strip()
        is_valid, error_msg = self._validate_class_name(class_name)

        if not is_valid:
            self._show_message("warning", "Błąd", error_msg)
            return

        self.classes[class_name] = {
            'name': class_name,
            'fields': [],
            'methods': [],
            'inherits': None,
            'compositions': [],
            'auto_eq_hash': False,
        }

        self.editor_class_name_input.clear()
        self.editor_class_name_input.setStyleSheet("")
        self._update_all_class_editor_views()

        items = self.editor_class_list.findItems(class_name, Qt.MatchFlag.MatchExactly)
        if items:
            list_item = items[0]
            self.editor_class_list.setCurrentItem(list_item)
            self.select_class_editor(list_item)

        self.classes_changed.emit()

    def delete_class(self):
        current_selection = self.editor_class_list.currentItem()
        if not current_selection:
            self._show_message("warning", "Błąd", "Nie wybrano klasy do usunięcia!")
            return

        class_to_delete = current_selection.text()
        dependent_classes = self._find_dependent_classes(class_to_delete)

        warning_msg = ""
        if dependent_classes:
            warning_msg += "\n\nUWAGA: Usunięcie tej klasy wpłynie na inne klasy:\n" + "\n".join(
                sorted(list(set(dependent_classes))))

        if not self._show_message("question", "Potwierdzenie usunięcia klasy",
                                  f"Czy na pewno chcesz usunąć klasę '{class_to_delete}' "
                                  f"oraz wszystkie powiązane z nią relacje i pola w innych klasach?{warning_msg}"):
            return

        self._remove_class_and_dependencies(class_to_delete)
        self._update_all_class_editor_views()
        self.classes_changed.emit()

    def _find_dependent_classes(self, class_to_delete: str) -> List[str]:
        dependent_classes = []
        for cls_name, cls_data in self.classes.items():
            if cls_name == class_to_delete:
                continue
            if cls_data.get('inherits') == class_to_delete:
                dependent_classes.append(f"- '{cls_name}' (dziedziczy)")
            for field in cls_data.get('fields', []):
                base_type = field['type'][5:-1] if field['type'].startswith("List[") else field['type']
                if base_type == class_to_delete:
                    dependent_classes.append(f"- '{cls_name}' (używa jako typ pola '{field['name']}')")
                    break
        return dependent_classes

    def _remove_class_and_dependencies(self, class_to_delete: str):
        try:
            del self.classes[class_to_delete]
        except KeyError:
            self._show_message("error", "Błąd", f"Nie znaleziono klasy '{class_to_delete}' do usunięcia.")
            return

        for cls_name, cls_data in self.classes.items():
            if cls_data.get('inherits') == class_to_delete:
                cls_data['inherits'] = None
            new_fields = []
            for field in cls_data.get('fields', []):
                base_type = field['type'][5:-1] if field['type'].startswith("List[") else field['type']
                if base_type != class_to_delete:
                    new_fields.append(field)
            cls_data['fields'] = new_fields

        if self.selected_class_editor == class_to_delete:
            self.selected_class_editor = None
            self.editor_class_list.setCurrentItem(None)
            self._enable_editor_panels(False)

    def select_class_editor(self, item: QListWidgetItem):
        if item is None:
            self.selected_class_editor = None
            self._enable_editor_panels(False)
            self.editor_fields_list.clear()
            self.editor_inheritance_target_combo.clear()
            return

        self.selected_class_editor = item.text()
        self._enable_editor_panels(True)
        self._update_editor_fields_list()
        self._update_editor_inheritance_targets()

        auto_eq_hash = self.classes[self.selected_class_editor].get('auto_eq_hash', False)
        self.editor_auto_eq_hash_checkbox.blockSignals(True)
        self.editor_auto_eq_hash_checkbox.setChecked(auto_eq_hash)
        self.editor_auto_eq_hash_checkbox.blockSignals(False)

    def _enable_editor_panels(self, enabled: bool):
        if hasattr(self, 'fields_management_panel'):
            self.fields_management_panel.setEnabled(enabled)
        if hasattr(self, 'inheritance_management_panel'):
            self.inheritance_management_panel.setEnabled(enabled)

    def add_field(self):
        if not self.selected_class_editor or not self.classes[self.selected_class_editor]:
            self._show_message("error", "Błąd wewnętrzny", "Nie wybrano klasy lub klasa nie istnieje.")
            return

        field_name = self.editor_field_name_input.text().strip()
        is_valid, error_msg = self._validate_field_name(field_name)

        if not is_valid:
            self._show_message("warning", "Błąd", error_msg)
            return

        base_field_type = self.editor_field_type_combo.currentText()
        if not base_field_type or base_field_type == "---":
            self._show_message("warning", "Błąd", "Nie wybrano typu pola.")
            return

        if base_field_type == self.selected_class_editor:
            self._show_message("warning", "Błąd",
                               f"Nie można dodać pola typu '{base_field_type}' w klasie '{self.selected_class_editor}'.\n"
                               "Klasa nie może zawierać pola tego samego typu co ona sama.")
            return

        container_type = self.editor_container_combo.currentData()
        final_field_type = self._create_container_type(base_field_type, container_type)

        if self._check_field_name_conflict(field_name):
            return

        self._add_field_to_class(field_name, final_field_type, base_field_type)
        self._clear_field_inputs()
        self._update_editor_fields_list()
        self.update_class_tree()
        self.classes_changed.emit()

    def _check_field_name_conflict(self, field_name: str) -> bool:
        all_fields_data = self._get_all_fields_recursive(self.selected_class_editor)
        existing_fields = {f['field']['name'] for f in all_fields_data}

        if field_name in existing_fields:
            conflict_source = "klasie nadrzędnej"
            for fdata in all_fields_data:
                if fdata['field']['name'] == field_name:
                    conflict_source = f"tej klasie ('{fdata['source']}')" if fdata[
                                                                                 'source'] == self.selected_class_editor else f"klasie '{fdata['source']}'"
                    break
            self._show_message("warning", "Błąd", f"Pole o nazwie '{field_name}' już istnieje w {conflict_source}.")
            return True
        return False

    def _add_field_to_class(self, field_name: str, final_field_type: str, base_field_type: str):
        self.classes[self.selected_class_editor]['fields'].append({
            'name': field_name,
            'type': final_field_type
        })

        is_composition = self.editor_composition_checkbox.isChecked()
        if is_composition and base_field_type in self.classes:
            compositions = self.classes[self.selected_class_editor].get('compositions', [])
            if base_field_type not in compositions:
                compositions.append(base_field_type)
                self.classes[self.selected_class_editor]['compositions'] = compositions

    def _clear_field_inputs(self):
        self.editor_field_name_input.clear()
        self.editor_field_name_input.setStyleSheet("")
        self.editor_composition_checkbox.setChecked(False)

    def delete_field(self):
        if not self.selected_class_editor:
            return

        selected_items = self.editor_fields_list.selectedItems()
        if not selected_items:
            self._show_message("warning", "Błąd", "Nie wybrano pola do usunięcia!")
            return

        item = selected_items[0]
        item_text = item.text()
        field_name = item_text.split(':')[0].strip()
        is_inherited = "(z " in item_text or not (item.flags() & Qt.ItemFlag.ItemIsSelectable)

        if is_inherited:
            source_class = "klasie nadrzędnej"
            if "(z " in item_text:
                source_class = f"klasie '{item_text.split('(z ')[1].split(')')[0]}'"
            self._show_message("warning", "Błąd",
                               f"Nie można usunąć pola '{field_name}', ponieważ jest dziedziczone z {source_class}.")
            return

        if self._remove_field_from_class(field_name):
            self._update_editor_fields_list()
            self.update_class_tree()
            self.classes_changed.emit()
        else:
            self._show_message("info", "Info", f"Nie znaleziono własnego pola o nazwie '{field_name}' do usunięcia.")

    def _remove_field_from_class(self, field_name: str) -> bool:
        class_data = self.classes[self.selected_class_editor]
        if 'fields' not in class_data:
            class_data['fields'] = []

        initial_len = len(class_data['fields'])
        class_data['fields'] = [
            field for field in class_data['fields']
            if field['name'] != field_name
        ]
        return len(class_data['fields']) < initial_len

    def add_relation(self):
        if not self.selected_class_editor:
            self._show_message("warning", "Błąd", "Najpierw wybierz klasę źródłową.")
            return

        target_class = self.editor_inheritance_target_combo.currentText()
        if not target_class:
            self._show_message("warning", "Błąd", "Nie wybrano klasy nadrzędnej.")
            return

        source_class = self.selected_class_editor

        if not self._validate_inheritance(source_class, target_class):
            return

        self._set_inheritance(source_class, target_class)

    def _validate_inheritance(self, source_class: str, target_class: str) -> bool:
        if source_class == target_class:
            self._show_message("warning", "Błąd", "Klasa nie może dziedziczyć po samej sobie!")
            return False

        if self._check_inheritance_path(source_class, target_class, "reverse"):
            self._show_message("warning", "Błąd cyklu",
                               f"Nie można ustawić dziedziczenia: '{target_class}' już dziedziczy po '{source_class}'.")
            return False

        if self._check_inheritance_path(source_class, target_class, "cycle"):
            self._show_message("warning", "Błąd cyklu",
                               f"Ustawienie dziedziczenia '{source_class}' -> '{target_class}' utworzyłoby cykl!")
            return False

        return True

    def _set_inheritance(self, source_class: str, target_class: str):
        source_data = self.classes[source_class]
        original_parent = source_data.get('inherits')

        if original_parent and original_parent != target_class:
            if not self._show_message("question", "Zmiana dziedziczenia",
                                      f"Klasa '{source_class}' już dziedziczy po '{original_parent}'. Zmienić na '{target_class}'?"):
                return
        elif original_parent == target_class:
            self._show_message("info", "Info", f"Klasa '{source_class}' już dziedziczy po '{target_class}'.")
            return

        source_data['inherits'] = target_class
        self._show_message("info", "Sukces", f"Ustawiono dziedziczenie: {source_class} -> {target_class}")
        self._update_all_class_editor_views()
        self.classes_changed.emit()

    def delete_relation(self):
        if not self.selected_class_editor:
            return

        source_class = self.selected_class_editor
        source_data = self.classes[source_class]
        current_inheritance = source_data.get('inherits')

        if not current_inheritance:
            self._show_message("warning", "Błąd", f"Klasa '{source_class}' aktualnie nie dziedziczy po żadnej klasie.")
            return

        if self._show_message("question", "Potwierdzenie",
                              f"Czy na pewno chcesz usunąć dziedziczenie klasy '{source_class}' po klasie '{current_inheritance}'?"):
            source_data['inherits'] = None
            self._show_message("info", "Sukces",
                               f"Usunięto dziedziczenie klasy '{source_class}' po '{current_inheritance}'.")
            self._update_all_class_editor_views()
            self.classes_changed.emit()

    def _get_all_fields_recursive(self, class_name: str, visited: Optional[set] = None) -> List[Dict[str, Any]]:
        if class_name not in self.classes:
            return []
        if visited is None:
            visited = set()
        if class_name in visited:
            return []

        visited.add(class_name)
        fields_map: Dict[str, Dict[str, Any]] = {}

        parent_class = self.classes[class_name].get('inherits')
        if parent_class:
            parent_fields_data = self._get_all_fields_recursive(parent_class, visited.copy())
            for field_info in parent_fields_data:
                fields_map[field_info['field']['name']] = field_info

        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source': class_name}

        visited.remove(class_name)
        return list(fields_map.values())

    def _update_all_class_editor_views(self):
        current_selected_class = self.selected_class_editor
        current_selected_target = self.editor_inheritance_target_combo.currentText()

        self._update_editor_class_list()

        if current_selected_class and current_selected_class in self.classes:
            items = self.editor_class_list.findItems(current_selected_class, Qt.MatchFlag.MatchExactly)
            if items:
                self.editor_class_list.setCurrentItem(items[0])
            else:
                self.selected_class_editor = None
                self._enable_editor_panels(False)
        else:
            self.selected_class_editor = None
            self._enable_editor_panels(False)

        self._update_editor_field_type_combo()
        self._update_editor_inheritance_targets()

        target_index = self.editor_inheritance_target_combo.findText(current_selected_target)
        if target_index != -1:
            self.editor_inheritance_target_combo.setCurrentIndex(target_index)
        elif self.editor_inheritance_target_combo.count() > 0:
            self.editor_inheritance_target_combo.setCurrentIndex(0)

        if self.selected_class_editor:
            self._update_editor_fields_list()
        else:
            self.editor_fields_list.clear()

        self.update_class_tree()

    def _update_editor_class_list(self):
        sorted_class_names = sorted(self.classes.keys())
        self._setup_list_widget(self.editor_class_list, sorted_class_names, self.selected_class_editor)

    def _update_editor_fields_list(self):
        self.editor_fields_list.clear()
        if not self.selected_class_editor or self.selected_class_editor not in self.classes:
            return

        all_fields_data = self._get_all_fields_recursive(self.selected_class_editor)

        def sort_key(field_info):
            is_own = (field_info['source'] == self.selected_class_editor)
            return (not is_own, field_info['field']['name'])

        sorted_fields_data = sorted(all_fields_data, key=sort_key)

        for field_info in sorted_fields_data:
            field = field_info['field']
            source = field_info['source']
            display_text = f"{field['name']}: {field['type']}"
            item = QListWidgetItem(display_text)

            if source != self.selected_class_editor:
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                item.setForeground(Qt.GlobalColor.gray)
                item.setText(display_text + f" (z {source})")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            self.editor_fields_list.addItem(item)

    def _update_editor_inheritance_targets(self):
        if not self.selected_class_editor:
            self.editor_inheritance_target_combo.clear()
            return

        available_targets = sorted([
            name for name in self.classes if name != self.selected_class_editor
        ])
        self._setup_combo_box(self.editor_inheritance_target_combo, available_targets)

    def update_class_tree(self):
        self.class_tree.clear()
        tree_items: Dict[str, QTreeWidgetItem] = {}

        def get_or_create_item(class_name: str) -> Optional[QTreeWidgetItem]:
            if class_name not in self.classes:
                return None
            if class_name in tree_items:
                return tree_items[class_name]

            class_data = self.classes[class_name]
            item = QTreeWidgetItem([class_name])
            tree_items[class_name] = item

            own_fields = class_data.get('fields', [])
            if own_fields:
                fields_node = QTreeWidgetItem(["Pola własne:"])
                font = fields_node.font(0)
                font.setItalic(True)
                fields_node.setFont(0, font)
                fields_node.setForeground(0, Qt.GlobalColor.darkGray)

                for field in sorted(own_fields, key=lambda x: x['name']):
                    field_item = QTreeWidgetItem([f"  {field['name']}: {field['type']}"])
                    fields_node.addChild(field_item)
                item.addChild(fields_node)

            return item

        root_items = []
        processed = set()
        sorted_class_names = sorted(self.classes.keys())

        for class_name in sorted_class_names:
            if class_name in processed:
                continue

            item = get_or_create_item(class_name)
            if not item:
                continue

            parent_name = self.classes[class_name].get('inherits')
            if parent_name and parent_name in self.classes:
                parent_item = get_or_create_item(parent_name)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    root_items.append(item)
            else:
                root_items.append(item)

            processed.add(class_name)

        self.class_tree.addTopLevelItems(root_items)
        self.class_tree.expandAll()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = ClassDiagramEditor()
    editor.show()
    sys.exit(app.exec())