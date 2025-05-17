import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFormLayout, QScrollArea, QFileDialog, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Dict, List, Optional, Any

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

    def _setup_main_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        self.generate_code_button = QPushButton("Generuj kod Pythona i zapisz")
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
        container_type = None
        base_type = type_str
        
        for container in ["List[", "Dict[", "Tuple[", "frozenset["]:
            if type_str.startswith(container) and type_str.endswith(']'):
                container_type = container[:-1]
                base_type = type_str[len(container):-1]
                break

        is_class_type = base_type in self.classes

        if container_type:
            base_hint = f"'{base_type}'" if is_class_type else base_type
            container_hint = f"{container_type}[{base_hint}]"
            if container_type == "Dict" and ":" not in base_type:
                container_hint = f"Dict[str, {base_hint}]"
            elif container_type == "Tuple":
                if not base_type.endswith(", ..."):
                    container_hint = f"Tuple[{base_hint}, ...]"
            return f"Optional[{container_hint}]" if is_optional else container_hint
        else:
            base_hint = f"'{base_type}'" if is_class_type else base_type
            return f"Optional[{base_hint}]" if is_optional else base_hint

    def _generate_python_code(self) -> str:
        code_lines = []
        if not self.classes:
            return ""
        imports = {"List", "Dict", "Tuple", "Set", "FrozenSet"}

        code_lines.append(f"from typing import {', '.join(sorted(imports))}")
        code_lines.append("\n")

        sorted_classes = self._sort_classes_by_inheritance()

        for class_name in sorted_classes:
            if class_name not in self.classes:
                continue

            class_data = self.classes[class_name]
            parent_name = class_data.get('inherits')
            compositions = class_data.get('compositions', [])
            own_fields = class_data.get('fields', [])

            parent_str = f"({parent_name})" if parent_name else ""
            code_lines.append(f"\nclass {class_name}{parent_str}:")

            all_fields_with_source = self._get_all_fields_recursive(
                class_name)

            required_init_params = []
            optional_init_params = []
            assigned_in_init = []

            parent_all_fields = []
            if parent_name:
                parent_all_fields_data = self._get_all_fields_recursive(parent_name)
                parent_all_fields = [f['field'] for f in parent_all_fields_data]

            processed_param_names = set()

            if parent_name:
                parent_compositions = self.classes[parent_name].get('compositions', [])
                for field in parent_all_fields:
                    if not self._is_composition_field(field['name'], field['type'], parent_compositions):
                        type_hint = self._get_type_hint_str(field['type'], False)
                        required_init_params.append(f"{field['name']}: {type_hint}")
                        processed_param_names.add(field['name'])

            for field_info in all_fields_with_source:
                field = field_info['field']
                source = field_info['source']
                is_own = (source == class_name)
                is_comp = self._is_composition_field(field['name'], field['type'], compositions)

                if not is_comp and field['name'] not in processed_param_names:
                    type_hint = self._get_type_hint_str(field['type'], False)
                    required_init_params.append(f"{field['name']}: {type_hint}")
                    processed_param_names.add(field['name'])
                if is_own:
                    assigned_in_init.append(field)

            if parent_name:
                parent_compositions = self.classes[parent_name].get('compositions', [])
                for field in parent_all_fields:
                    if self._is_composition_field(field['name'], field['type'], parent_compositions):
                        type_hint = self._get_type_hint_str(field['type'], True)
                        optional_init_params.append(f"{field['name']}: {type_hint} = None")
                        processed_param_names.add(field['name'])

            for field_info in all_fields_with_source:
                field = field_info['field']
                source = field_info['source']
                is_own = (source == class_name)
                is_comp = self._is_composition_field(field['name'], field['type'], compositions)

                if is_comp and field['name'] not in processed_param_names:
                    type_hint = self._get_type_hint_str(field['type'], True)
                    optional_init_params.append(f"{field['name']}: {type_hint} = None")
                    processed_param_names.add(field['name'])
                if is_own and is_comp and field not in assigned_in_init:
                    assigned_in_init.append(field)

            if not required_init_params and not optional_init_params and not parent_name:
                if not own_fields:
                    code_lines.append("    pass")
                    continue

            init_params = ['self'] + required_init_params + optional_init_params
            code_lines.append(f"    def __init__({', '.join(init_params)}):")

            if parent_name:
                super_args = []
                parent_params_names = {f['name'] for f in parent_all_fields}

                parent_compositions = self.classes[parent_name].get('compositions', [])
                for field in parent_all_fields:
                    if not self._is_composition_field(field['name'], field['type'], parent_compositions):
                        if field['name'] in processed_param_names:
                            super_args.append(field['name'])
                for field in parent_all_fields:
                    if self._is_composition_field(field['name'], field['type'], parent_compositions):
                        if field['name'] in processed_param_names:
                            super_args.append(field['name'])

                if super_args:
                    code_lines.append(f"        super().__init__({', '.join(super_args)})")
                elif parent_all_fields:
                    code_lines.append(f"        super().__init__()")

            if not assigned_in_init and not parent_name and not required_init_params and not optional_init_params:
                code_lines.append("        pass")
            else:
                init_body_empty = True
                for field in sorted(assigned_in_init, key=lambda x: x['name']):
                    init_body_empty = False
                    is_comp = self._is_composition_field(field['name'], field['type'], compositions)
                    is_list_type = field['type'].startswith("List[")

                    if is_comp and is_list_type:
                        code_lines.append(
                            f"        self.{field['name']}: {self._get_type_hint_str(field['type'], True)} = {field['name']} if {field['name']} is not None else []")
                    elif is_comp and not is_list_type:
                        code_lines.append(
                            f"        self.{field['name']}: {self._get_type_hint_str(field['type'], True)} = {field['name']}")
                    elif not is_comp:
                        code_lines.append(
                            f"        self.{field['name']}: {self._get_type_hint_str(field['type'], False)} = {field['name']}")

                if init_body_empty and not parent_name:
                    code_lines.append("        pass")

        return "\n".join(code_lines)

    def _sort_classes_by_inheritance(self) -> List[str]:
        class_order = []
        remaining_classes = set(self.classes.keys())
        processing = set()

        def add_class_to_order(cls_name):
            if cls_name in class_order:
                return
            if cls_name in processing:
                print(f"Warning: Circular inheritance detected involving {cls_name}")
                return

            processing.add(cls_name)
            parent_name = self.classes[cls_name].get('inherits')
            if parent_name and parent_name in self.classes:
                add_class_to_order(parent_name)

            processing.remove(cls_name)
            if cls_name not in class_order:
                class_order.append(cls_name)

        sorted_keys = sorted(list(remaining_classes))
        for cls in sorted_keys:
            if cls not in class_order:
                add_class_to_order(cls)

        if len(class_order) != len(self.classes):
            print("Warning: Some classes might be missing from sorted order (e.g., invalid parent reference)")
            missing = set(self.classes.keys()) - set(class_order)
            class_order.extend(sorted(list(missing)))

        return class_order

    def _save_python_code(self):
        if not self.classes:
            QMessageBox.information(self, "Brak Klas", "Nie zdefiniowano żadnych klas do wygenerowania kodu.")
            return

        try:
            generated_code = self._generate_python_code()
        except Exception as e:
            QMessageBox.critical(self, "Błąd Generowania Kodu", f"Wystąpił błąd podczas generowania kodu:\n{e}")
            import traceback
            traceback.print_exc()
            return

        if not generated_code:
            QMessageBox.information(self, "Brak kodu",
                                    "Generowanie nie zwróciło żadnego kodu (sprawdź ostrzeżenia w konsoli).")
            return

        default_filename = "wygenerowany_kod.py"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz kod Pythona",
            default_filename,
            "Python Files (*.py);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(generated_code)
                QMessageBox.information(self, "Sukces", f"Kod Pythona został zapisany do:\n{file_path}")
            except IOError as e:
                QMessageBox.critical(self, "Błąd Zapisu", f"Nie można zapisać pliku:\n{e}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd Zapisu", f"Wystąpił nieoczekiwany błąd podczas zapisu:\n{e}")

    def _create_class_editor_widget(self) -> QWidget:
        editor_widget = QWidget()
        editor_layout = QHBoxLayout(editor_widget)

        side_panel = QWidget()
        side_panel.setFixedWidth(350)
        self.side_layout = QVBoxLayout(side_panel)
        self.side_layout.setContentsMargins(5, 5, 5, 5)
        self.side_layout.setSpacing(10)

        self.class_management_panel = self._create_class_management_panel()
        self.fields_management_panel = self._create_fields_management_panel()
        self.relations_management_panel = self._create_relations_management_panel()

        self.side_layout.addWidget(self.class_management_panel)
        self.side_layout.addWidget(self.fields_management_panel)
        self.side_layout.addWidget(self.relations_management_panel)
        self.side_layout.addStretch()

        self.class_tree = QTreeWidget()
        self.class_tree.setHeaderLabel("Struktura klas")

        editor_layout.addWidget(side_panel)
        editor_layout.addWidget(self.class_tree)

        return editor_widget

    def _create_class_management_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("<b>Zarządzanie klasami:</b>"))
        self.editor_class_name_input = QLineEdit()
        self.editor_class_name_input.setPlaceholderText("Nazwa nowej klasy (Wielka litera)")
        self.editor_add_class_btn = QPushButton("Dodaj klasę")

        self.editor_class_list = QListWidget()
        self.editor_delete_class_btn = QPushButton("Usuń zaznaczoną klasę")

        layout.addWidget(self.editor_class_name_input)
        layout.addWidget(self.editor_add_class_btn)
        layout.addWidget(QLabel("Istniejące klasy:"))
        layout.addWidget(self.editor_class_list)
        layout.addWidget(self.editor_delete_class_btn)

        self.editor_add_class_btn.clicked.connect(self.add_class)
        self.editor_class_list.itemClicked.connect(self.select_class_editor)
        self.editor_delete_class_btn.clicked.connect(self.delete_class)
        return panel

    def _create_fields_management_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("<b>Zarządzanie polami (dla wybranej klasy):</b>"))
        self.editor_field_name_input = QLineEdit()
        self.editor_field_name_input.setPlaceholderText("Nazwa nowego pola (mała litera)")

        self.editor_field_type_combo = QComboBox()
        self._update_editor_field_type_combo()

        self.editor_container_combo = QComboBox()
        self.editor_container_combo.addItem("Pojedyncza wartość", None)
        self.editor_container_combo.addItem("Lista (List[typ])", "List")
        self.editor_container_combo.addItem("Słownik (Dict[klucz,wartość])", "Dict")
        self.editor_container_combo.addItem("Krotka (Tuple[typ, ...])", "Tuple")
        self.editor_container_combo.addItem("FrozenSet (Frozenset[typ])", "Frozenset")
        self.editor_container_combo.addItem("Set (Set[typ])", "Set")

        type_layout = QHBoxLayout()
        type_layout.addWidget(self.editor_field_type_combo, 1)
        type_layout.addWidget(self.editor_container_combo)

        self.editor_add_field_btn = QPushButton("Dodaj pole")

        self.editor_fields_list = QListWidget()
        self.editor_delete_field_btn = QPushButton("Usuń zaznaczone pole")

        layout.addWidget(self.editor_field_name_input)
        layout.addWidget(QLabel("Typ pola:"))
        layout.addLayout(type_layout)
        layout.addWidget(self.editor_add_field_btn)
        layout.addWidget(QLabel("Pola w klasie (własne i dziedziczone):"))
        layout.addWidget(self.editor_fields_list)
        layout.addWidget(self.editor_delete_field_btn)

        self.editor_add_field_btn.clicked.connect(self.add_field)
        self.editor_delete_field_btn.clicked.connect(self.delete_field)

        panel.setEnabled(False)

        return panel

    def _update_editor_field_type_combo(self):
        current_selection = self.editor_field_type_combo.currentText()
        self.editor_field_type_combo.clear()
        basic_types = ["str", "int", "float", "bool", "complex"]
        self.editor_field_type_combo.addItems(basic_types)

        class_names = sorted(self.classes.keys())
        if class_names:
            self.editor_field_type_combo.insertSeparator(len(basic_types))
            self.editor_field_type_combo.addItems(class_names)

        index = self.editor_field_type_combo.findText(current_selection)
        if index != -1:
            self.editor_field_type_combo.setCurrentIndex(index)
        elif self.editor_field_type_combo.count() > 0:
            self.editor_field_type_combo.setCurrentIndex(0)

    def _create_relations_management_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("<b>Zarządzanie relacjami (dla wybranej klasy):</b>"))

        self.editor_relation_type_combo = QComboBox()
        self.editor_relation_type_combo.addItems(["Dziedziczenie", "Kompozycja"])
        self.editor_relation_type_combo.currentTextChanged.connect(
            self._update_relation_delete_button_text)

        self.editor_relation_target_combo = QComboBox()

        self.editor_add_relation_btn = QPushButton("Dodaj relację")
        self.editor_delete_relation_btn = QPushButton("Usuń relację")

        layout.addWidget(QLabel("Typ relacji:"))
        layout.addWidget(self.editor_relation_type_combo)
        layout.addWidget(QLabel("Klasa docelowa:"))
        layout.addWidget(self.editor_relation_target_combo)
        layout.addWidget(self.editor_add_relation_btn)
        layout.addWidget(self.editor_delete_relation_btn)

        self.editor_add_relation_btn.clicked.connect(self.add_relation)
        self.editor_delete_relation_btn.clicked.connect(self.delete_relation)

        panel.setEnabled(False)

        return panel

    def _update_relation_delete_button_text(self, relation_type):
        if relation_type == "Dziedziczenie":
            self.editor_delete_relation_btn.setText("Usuń dziedziczenie")
        elif relation_type == "Kompozycja":
            self.editor_delete_relation_btn.setText("Usuń kompozycję z wybranej klasy")
        else:
            self.editor_delete_relation_btn.setText("Usuń relację")

    def add_class(self):
        class_name = self.editor_class_name_input.text().strip()
        if not class_name:
            QMessageBox.warning(self, "Błąd", "Nazwa klasy nie może być pusta!")
            return
        if not class_name[0].isupper():
            QMessageBox.warning(self, "Błąd", "Nazwa klasy musi zaczynać się wielką literą!")
            return
        if ' ' in class_name or not class_name.isidentifier():
            QMessageBox.warning(self, "Błąd",
                                "Nazwa klasy zawiera niedozwolone znaki (np. spacje) lub jest słowem kluczowym Pythona.")
            return

        if class_name in self.classes:
            QMessageBox.warning(self, "Błąd", "Klasa o tej nazwie już istnieje!")
            return

        self.classes[class_name] = {
            'name': class_name,
            'fields': [],
            'methods': [],
            'inherits': None,
            'compositions': []
        }
        self.editor_class_name_input.clear()
        self.editor_class_name_input.setStyleSheet("")

        self._update_all_class_editor_views()

        items = self.editor_class_list.findItems(class_name, Qt.MatchFlag.MatchExactly)
        if items:
            list_item = items[0]
            self.editor_class_list.setCurrentItem(list_item)
            self.select_class_editor(list_item)
        else:
            self.selected_class_editor = None
            self._enable_editor_panels(False)

        self.classes_changed.emit()

    def delete_class(self):
        current_selection = self.editor_class_list.currentItem()
        if not current_selection:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy do usunięcia!")
            return
        class_to_delete = current_selection.text()

        dependent_classes = []
        dependent_objects = []

        for cls_name, cls_data in self.classes.items():
            if cls_name == class_to_delete: continue
            if cls_data.get('inherits') == class_to_delete:
                dependent_classes.append(f"- '{cls_name}' (dziedziczy)")
            if class_to_delete in cls_data.get('compositions', []):
                dependent_classes.append(f"- '{cls_name}' (kompozycja)")
            for field in cls_data.get('fields', []):
                base_type = field['type'][5:-1] if field['type'].startswith("List[") else field['type']
                if base_type == class_to_delete:
                    dependent_classes.append(f"- '{cls_name}' (używa jako typ pola '{field['name']}')")
                    break

        warning_msg = ""
        if dependent_classes:
            warning_msg += "\n\nUWAGA: Usunięcie tej klasy wpłynie na inne klasy:\n" + "\n".join(
                sorted(list(set(dependent_classes))))

        reply = QMessageBox.question(self, "Potwierdzenie usunięcia klasy",
                                     f"Czy na pewno chcesz usunąć klasę '{class_to_delete}' "
                                     f"oraz wszystkie powiązane z nią relacje i pola w innych klasach?{warning_msg}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        try:
            del self.classes[class_to_delete]
        except KeyError:
            QMessageBox.critical(self, "Błąd",
                                 f"Nie znaleziono klasy '{class_to_delete}' do usunięcia (błąd wewnętrzny).")
            return

        for cls_name, cls_data in self.classes.items():
            if cls_data.get('inherits') == class_to_delete:
                cls_data['inherits'] = None
            cls_data['compositions'] = [c for c in cls_data.get('compositions', []) if c != class_to_delete]
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

        self._update_all_class_editor_views()
        self.classes_changed.emit()

    def select_class_editor(self, item: QListWidgetItem):
        if item is None:
            self.selected_class_editor = None
            self._enable_editor_panels(False)
            self.editor_fields_list.clear()
            self.editor_relation_target_combo.clear()
            return

        self.selected_class_editor = item.text()
        self._enable_editor_panels(True)
        self._update_editor_fields_list()
        self._update_editor_relation_targets()
        self._update_relation_delete_button_text(self.editor_relation_type_combo.currentText())

    def _enable_editor_panels(self, enabled: bool):
        if hasattr(self, 'fields_management_panel'):
            self.fields_management_panel.setEnabled(enabled)
        if hasattr(self, 'relations_management_panel'):
            self.relations_management_panel.setEnabled(enabled)

    def add_field(self):
        if not self.selected_class_editor or not self.classes[self.selected_class_editor]:
            QMessageBox.critical(self, "Błąd wewnętrzny", "Nie wybrano klasy lub klasa nie istnieje.")
            return

        field_name = self.editor_field_name_input.text().strip()
        if not field_name:
            QMessageBox.warning(self, "Błąd", "Nazwa pola nie może być pusta.")
            return
        if not field_name[0].islower():
            QMessageBox.warning(self, "Błąd", "Nazwa pola musi zaczynać się małą literą.")
            return
        if ' ' in field_name or not field_name.isidentifier():
            QMessageBox.warning(self, "Błąd", "Nazwa pola zawiera niedozwolone znaki lub jest słowem kluczowym.")
            return

        base_field_type = self.editor_field_type_combo.currentText()
        if not base_field_type:
            QMessageBox.warning(self, "Błąd", "Nie wybrano typu pola.")
            return

        if base_field_type == self.selected_class_editor:
            QMessageBox.warning(self, "Błąd", 
                            f"Nie można dodać pola typu '{base_field_type}' w klasie '{self.selected_class_editor}'.\n"
                            "Klasa nie może zawierać pola tego samego typu co ona sama.")
            return

        container_type = self.editor_container_combo.currentData()
        
        if container_type == "List":
            final_field_type = f"List[{base_field_type}]"
        elif container_type == "Dict":
            final_field_type = f"Dict[str, {base_field_type}]"
        elif container_type == "Tuple":
            final_field_type = f"Tuple[{base_field_type}, ...]"
        elif container_type == "FrozenSet":
            final_field_type = f"FrozenSet[{base_field_type}]"
        elif container_type == "Set":
            final_field_type = f"Set[{base_field_type}]"
        else:
            final_field_type = base_field_type

        all_fields_data = self._get_all_fields_recursive(self.selected_class_editor)
        existing_fields = {f['field']['name'] for f in all_fields_data}
        if field_name in existing_fields:
            conflict_source = "klasie nadrzędnej"
            for fdata in all_fields_data:
                if fdata['field']['name'] == field_name:
                    conflict_source = f"tej klasie ('{fdata['source']}')" if fdata['source'] == self.selected_class_editor else f"klasie '{fdata['source']}'"
                    break
            QMessageBox.warning(self, "Błąd", f"Pole o nazwie '{field_name}' już istnieje w {conflict_source}.")
            return

        self.classes[self.selected_class_editor]['fields'].append({
            'name': field_name,
            'type': final_field_type
        })

        self.editor_field_name_input.clear()
        self.editor_field_name_input.setStyleSheet("")
        self._update_editor_fields_list()
        self.update_class_tree()
        self.classes_changed.emit()

    def delete_field(self):
        if not self.selected_class_editor: 
            return

        selected_items = self.editor_fields_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie wybrano pola do usunięcia!")
            return

        item = selected_items[0]
        item_text = item.text()
        field_name = item_text.split(':')[0].strip()

        is_inherited = "(z " in item_text or not (item.flags() & Qt.ItemFlag.ItemIsSelectable)

        if is_inherited:
            source_class = "klasie nadrzędnej"
            if "(z " in item_text:
                source_class = f"klasie '{item_text.split('(z ')[1].split(')')[0]}'"
            QMessageBox.warning(self, "Błąd",
                            f"Nie można usunąć pola '{field_name}', ponieważ jest dziedziczone z {source_class}. Usuń je w klasie bazowej.")
            return

        field_data = None
        class_data = self.classes[self.selected_class_editor]
        
        if 'fields' not in class_data:
            class_data['fields'] = []
        
        for f in class_data['fields']:
            if f['name'] == field_name:
                field_data = f
                break

        if 'compositions' not in class_data:
            class_data['compositions'] = []

        if field_data and self._is_composition_field(field_name, field_data['type'], class_data['compositions']):
            reply = QMessageBox.question(self, "Pole kompozycji",
                                    f"Pole '{field_name}' reprezentuje kompozycję z klasą '{field_data['type']}'. "
                                    f"Usunięcie tego pola usunie również relację kompozycji (jeśli to ostatnie takie pole). Kontynuować?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        initial_len = len(class_data['fields'])
        class_data['fields'] = [
            field for field in class_data['fields']
            if field['name'] != field_name
        ]

        if field_data and self._is_composition_field(field_name, field_data['type'], class_data['compositions']):
            target_class = field_data['type']
            remaining_comp_fields = [
                f for f in class_data['fields']
                if self._is_composition_field(f['name'], f['type'], [target_class])
            ]
            if not remaining_comp_fields:
                class_data['compositions'] = [
                    c for c in class_data['compositions']
                    if c != target_class
                ]
                QMessageBox.information(self, "Kompozycja usunięta",
                                    f"Usunięto również relację kompozycji z '{target_class}', ponieważ było to ostatnie pole reprezentujące tę relację.")

        if len(class_data['fields']) < initial_len:
            self._update_editor_fields_list()
            self.update_class_tree()
            self.classes_changed.emit()
        else:
            QMessageBox.information(self, "Info", f"Nie znaleziono własnego pola o nazwie '{field_name}' do usunięcia.")

    def _check_reverse_inheritance(self, source: str, target: str) -> bool:
        current = target
        visited = set()
        
        while current in self.classes:
            if current == source:
                return True
            if current in visited:
                return False
            visited.add(current)
            current = self.classes[current].get('inherits')
        
        return False

    def _check_composition_cycle(self, source: str, target: str) -> bool:
        queue = [target]
        visited = set()

        while queue:
            current = queue.pop(0)

            if current == source:
                return True

            if current in visited:
                continue
            visited.add(current)

            if current not in self.classes:
                continue

            class_data = self.classes[current]

            queue.extend(class_data.get('compositions', []))

            parent = class_data.get('inherits')
            if parent:
                queue.append(parent)

        return False

    def add_relation(self):
        if not self.selected_class_editor:
            QMessageBox.warning(self, "Błąd", "Najpierw wybierz klasę źródłową.")
            return

        target_class = self.editor_relation_target_combo.currentText()
        if not target_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy docelowej relacji.")
            return

        relation_type = self.editor_relation_type_combo.currentText()
        source_class = self.selected_class_editor
        source_data = self.classes[source_class]

        if source_class == target_class:
            QMessageBox.warning(self, "Błąd", "Klasa nie może mieć relacji z samą sobą!")
            return

        if relation_type == "Dziedziczenie":
            if self._check_reverse_inheritance(source_class, target_class):
                QMessageBox.warning(self, "Błąd cyklu",
                                    f"Nie można ustawić dziedziczenia: '{target_class}' już dziedziczy (bezpośrednio lub pośrednio) po '{source_class}'.")
                return

            if self._check_inheritance_cycle(source_class, target_class):
                QMessageBox.warning(self, "Błąd cyklu",
                                    f"Ustawienie dziedziczenia '{source_class}' -> '{target_class}' utworzyłoby cykl dziedziczenia!")
                return

            original_parent = source_data.get('inherits')
            if original_parent and original_parent != target_class:
                reply = QMessageBox.question(
                    self, "Zmiana dziedziczenia",
                    f"Klasa '{source_class}' już dziedziczy po '{original_parent}'. Zmienić na '{target_class}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            elif original_parent == target_class:
                QMessageBox.information(self, "Info", f"Klasa '{source_class}' już dziedziczy po '{target_class}'.")
                return

            source_data['inherits'] = target_class
            QMessageBox.information(self, "Sukces", f"Ustawiono dziedziczenie: {source_class} -> {target_class}")

        elif relation_type == "Kompozycja":
            if self._check_composition_cycle(source_class, target_class):
                QMessageBox.warning(self, "Błąd cyklu",
                                    f"Dodanie kompozycji '{source_class}' --<> '{target_class}' utworzyłoby cykl zależności (przez kompozycje i/lub dziedziczenie)!")
                return

            field_name = self._generate_composition_field_name(source_class, target_class)
            field_type = target_class

            source_data.setdefault('fields', []).append({'name': field_name, 'type': field_type})
            if target_class not in source_data.setdefault('compositions', []):
                source_data['compositions'].append(target_class)

            QMessageBox.information(self, "Sukces",
                                    f"Dodano kompozycję: {source_class} --<> {target_class} (utworzono pole '{field_name}': {field_type})")

        self._update_all_class_editor_views()
        self.classes_changed.emit()

    def delete_relation(self):
        if not self.selected_class_editor: return

        relation_type = self.editor_relation_type_combo.currentText()
        source_class = self.selected_class_editor
        source_data = self.classes[source_class]

        if relation_type == "Dziedziczenie":
            current_inheritance = source_data.get('inherits')
            if not current_inheritance:
                QMessageBox.warning(self, "Błąd", f"Klasa '{source_class}' aktualnie nie dziedziczy po żadnej klasie.")
                return

            reply = QMessageBox.question(self, "Potwierdzenie",
                                         f"Czy na pewno chcesz usunąć dziedziczenie klasy '{source_class}' po klasie '{current_inheritance}'?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                source_data['inherits'] = None
                QMessageBox.information(self, "Sukces",
                                        f"Usunięto dziedziczenie klasy '{source_class}' po '{current_inheritance}'.")
                self._update_all_class_editor_views()
                self.classes_changed.emit()

        elif relation_type == "Kompozycja":
            target_class = self.editor_relation_target_combo.currentText()
            if not target_class:
                QMessageBox.warning(self, "Błąd", "Nie wybrano klasy docelowej dla kompozycji do usunięcia.")
                return

            current_compositions = source_data.get('compositions', [])
            if target_class not in current_compositions:
                QMessageBox.warning(self, "Błąd",
                                    f"Klasa '{source_class}' nie ma zdefiniowanej relacji kompozycji z '{target_class}'.\n(Mogą istnieć pola tego typu, ale bez formalnej relacji kompozycji).")
                return

            composition_fields_to_remove = [
                f for f in source_data.get('fields', [])
                if self._is_composition_field(f['name'], f['type'], [target_class])
            ]

            if not composition_fields_to_remove:
                reply = QMessageBox.question(self, "Niespójność",
                                             f"Istnieje relacja kompozycji z '{target_class}', ale nie znaleziono powiązanych pól (np. 'composed_{target_class.lower()}_N').\n"
                                             f"Czy chcesz usunąć tylko formalną relację kompozycji?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.Yes)
                if reply == QMessageBox.StandardButton.No: return

            else:
                field_names = [f"'{f['name']}'" for f in composition_fields_to_remove]
                reply = QMessageBox.question(self, "Potwierdzenie",
                                             f"Czy na pewno chcesz usunąć kompozycję klasy '{source_class}' z '{target_class}'?\n"
                                             f"Spowoduje to usunięcie następujących pól: {', '.join(field_names)}.",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)

                if reply == QMessageBox.StandardButton.No:
                    return

                field_names_set = {f['name'] for f in composition_fields_to_remove}
                source_data['fields'] = [
                    f for f in source_data.get('fields', [])
                    if f['name'] not in field_names_set
                ]

            source_data['compositions'] = [c for c in current_compositions if c != target_class]

            QMessageBox.information(self, "Sukces",
                                    f"Usunięto kompozycję z '{target_class}'" + (
                                        f" oraz powiązane pola: {', '.join(field_names)}." if composition_fields_to_remove else "."))
            self._update_all_class_editor_views()
            self.classes_changed.emit()

    def _check_inheritance_cycle(self, child_class: str, new_parent: str) -> bool:
        current = new_parent
        visited = set()
        
        while current in self.classes:
            if current == child_class:
                return True
            if current in visited:
                return False
            visited.add(current)
            current = self.classes[current].get('inherits')
        
        return False

    def _get_all_fields_recursive(self, class_name: str, visited: Optional[set] = None) -> List[Dict[str, Any]]:
        if class_name not in self.classes: return []

        if visited is None: visited = set()
        if class_name in visited:
            print(f"Warning: Cycle detected involving class '{class_name}' while getting fields. Stopping recursion.")
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

    def _is_composition_field(self, field_name: str, field_type: str, composition_targets: List[str]) -> bool:
        base_type = field_type[5:-1] if field_type.startswith("List[") else field_type
        if base_type not in composition_targets:
            return False

        expected_prefix = f"composed_{base_type.lower()}_"
        return field_name.startswith(expected_prefix)

    def _generate_composition_field_name(self, source_class: str, target_class: str) -> str:
        if not self.selected_class_editor: return f"error_no_source_selected"

        base_name = f"composed_{target_class.lower()}"
        counter = 1
        field_name = f"{base_name}_{counter}"

        all_fields_data = self._get_all_fields_recursive(self.selected_class_editor)
        existing_field_names = {f['field']['name'] for f in all_fields_data}

        while field_name in existing_field_names:
            counter += 1
            field_name = f"{base_name}_{counter}"

        return field_name

    def _update_all_class_editor_views(self):
        current_selected_class = self.selected_class_editor
        current_selected_target = self.editor_relation_target_combo.currentText()

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
        self._update_editor_relation_targets()

        target_index = self.editor_relation_target_combo.findText(current_selected_target)
        if target_index != -1:
            self.editor_relation_target_combo.setCurrentIndex(target_index)
        elif self.editor_relation_target_combo.count() > 0:
            self.editor_relation_target_combo.setCurrentIndex(0)

        if self.selected_class_editor:
            self._update_editor_fields_list()
        else:
            self.editor_fields_list.clear()

        self.update_class_tree()

    def _update_editor_class_list(self):
        self.editor_class_list.clear()
        sorted_class_names = sorted(self.classes.keys())
        self.editor_class_list.addItems(sorted_class_names)

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

    def _update_editor_relation_targets(self):
        self.editor_relation_target_combo.clear()
        if not self.selected_class_editor: return

        available_targets = sorted([
            name for name in self.classes if name != self.selected_class_editor
        ])
        self.editor_relation_target_combo.addItems(available_targets)

    def update_class_tree(self):
        self.class_tree.clear()
        tree_items: Dict[str, QTreeWidgetItem] = {}

        def get_or_create_item(class_name: str) -> Optional[QTreeWidgetItem]:
            if class_name not in self.classes: return None
            if class_name in tree_items: return tree_items[class_name]

            class_data = self.classes[class_name]
            item = QTreeWidgetItem([class_name])
            tree_items[class_name] = item

            own_fields = class_data.get('fields', [])
            compositions = class_data.get('compositions', [])
            if own_fields:
                fields_node = QTreeWidgetItem(["Pola własne:"])
                font = fields_node.font(0)
                font.setItalic(True)
                fields_node.setFont(0, font)
                fields_node.setForeground(0, Qt.GlobalColor.darkGray)

                added_field = False
                for field in sorted(own_fields, key=lambda x: x['name']):
                    if not self._is_composition_field(field['name'], field['type'], compositions):
                        field_item = QTreeWidgetItem([f"  {field['name']}: {field['type']}"])
                        fields_node.addChild(field_item)
                        added_field = True

                if added_field:
                    item.addChild(fields_node)

            if compositions:
                comp_node = QTreeWidgetItem(["Kompozycje:"])
                font = comp_node.font(0)
                font.setItalic(True)
                comp_node.setFont(0, font)
                comp_node.setForeground(0, Qt.GlobalColor.darkBlue)
                item.addChild(comp_node)

                for comp_target in sorted(compositions):
                    comp_fields = [f['name'] for f in own_fields if
                                   self._is_composition_field(f['name'], f.get('type', ''), [comp_target])]
                    field_info = f" (pola: {', '.join(comp_fields)})" if comp_fields else ""
                    comp_child = QTreeWidgetItem([f"  <>-- {comp_target}{field_info}"])
                    comp_node.addChild(comp_child)

            return item

        root_items = []
        processed = set()

        sorted_class_names = sorted(self.classes.keys())
        for class_name in sorted_class_names:
            if class_name in processed: continue

            item = get_or_create_item(class_name)
            if not item: continue

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