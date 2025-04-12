import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFormLayout, QScrollArea, QFileDialog, QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Dict, List, Optional, Any, Tuple
import random
import string

# Reusing types from the original program
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any]
ObjectsDict = Dict[str, ObjectData]


class ObjectGeneratorApp(QMainWindow):
    objects_changed = pyqtSignal()

    def __init__(self, classes: ClassesDict):
        super().__init__()
        self.setWindowTitle("Generator Obiektów")
        self.setGeometry(100, 100, 1000, 700)

        self.classes = classes
        self.objects: ObjectsDict = {}

        self._setup_ui()
        self._update_object_class_combo()
        self._update_object_tree()

        # Connect signals
        self.objects_changed.connect(self._update_object_tree)
        self.objects_changed.connect(self._update_composition_combos)

    def _setup_ui(self):
        """Konfiguruje główny interfejs użytkownika."""
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

        # Create object button
        self.create_object_btn = QPushButton("Utwórz/Zaktualizuj obiekt")
        self.create_object_btn.clicked.connect(self._create_or_update_object)
        left_layout.addWidget(self.create_object_btn)

        # --- Right Panel: Object List ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Istniejące obiekty:"))
        self.object_tree = QTreeWidget()
        self.object_tree.setHeaderLabels(["Właściwość", "Wartość"])
        self.object_tree.setColumnWidth(0, 200)
        right_layout.addWidget(self.object_tree)

        # Object actions
        btn_layout = QHBoxLayout()
        self.edit_object_btn = QPushButton("Edytuj zaznaczony")
        self.edit_object_btn.clicked.connect(self._edit_selected_object)
        btn_layout.addWidget(self.edit_object_btn)

        self.delete_object_btn = QPushButton("Usuń zaznaczony")
        self.delete_object_btn.clicked.connect(self._delete_selected_object)
        btn_layout.addWidget(self.delete_object_btn)
        right_layout.addLayout(btn_layout)

        # Export buttons
        export_layout = QHBoxLayout()
        self.export_json_btn = QPushButton("Eksportuj do JSON")
        self.export_json_btn.clicked.connect(self._export_to_json)
        export_layout.addWidget(self.export_json_btn)

        self.export_python_btn = QPushButton("Eksportuj do Pythona")
        self.export_python_btn.clicked.connect(self._export_to_python)
        export_layout.addWidget(self.export_python_btn)
        right_layout.addLayout(export_layout)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

    def _update_object_class_combo(self):
        """Aktualizuje listę klas w ComboBoxie."""
        self.object_class_combo.clear()
        self.object_class_combo.addItems(sorted(self.classes.keys()))

    def _update_object_creation_form(self):
        """Aktualizuje formularz tworzenia obiektu na podstawie wybranej klasy."""
        # Clear previous widgets
        while self.object_fields_layout.count():
            child = self.object_fields_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        selected_class = self.object_class_combo.currentText()
        if not selected_class:
            return

        # Get all fields (own and inherited)
        all_fields = self._get_all_fields_recursive(selected_class)

        if not all_fields:
            self.object_fields_layout.addRow(QLabel("Brak pól do wypełnienia."))
            return

        # Sort fields by name
        all_fields.sort(key=lambda x: x['field']['name'])

        for field_info in all_fields:
            field = field_info['field']
            field_name = field['name']
            field_type = field['type']

            label = QLabel(f"{field_name} ({field_type})")

            # Create appropriate input widget based on field type
            if field_type == "int":
                input_widget = QSpinBox()
                input_widget.setRange(-1000000, 1000000)
            elif field_type == "float":
                input_widget = QLineEdit()
                input_widget.setPlaceholderText("Wprowadź liczbę zmiennoprzecinkową")
            elif field_type == "bool":
                input_widget = QCheckBox()
            elif field_type == "str":
                input_widget = QLineEdit()
            elif field_type in ["list", "dict"]:
                input_widget = QLineEdit()
                input_widget.setPlaceholderText(f"Wprowadź {field_type} jako JSON")
            elif field_type in self.classes:  # Composition
                input_widget = QComboBox()
                input_widget.addItem("(Brak)")
                # Add existing objects of this type
                for obj_name, obj_data in self.objects.items():
                    if obj_data['class'] == field_type:
                        input_widget.addItem(obj_name)
            else:  # Unknown type
                input_widget = QLineEdit()

            self.object_fields_layout.addRow(label, input_widget)

    def _get_all_fields_recursive(self, class_name: str, visited=None) -> List[Dict[str, Any]]:
        """Rekurencyjnie pobiera wszystkie pola klasy (własne i dziedziczone)."""
        if class_name not in self.classes:
            return []

        if visited is None:
            visited = set()

        if class_name in visited:
            return []

        visited.add(class_name)

        fields_map = {}

        # Get fields from parent first
        parent_class = self.classes[class_name].get('inherits')
        if parent_class:
            parent_fields = self._get_all_fields_recursive(parent_class, visited.copy())
            for field_info in parent_fields:
                fields_map[field_info['field']['name']] = field_info

        # Add own fields (overwriting inherited ones with same name)
        own_fields = self.classes[class_name].get('fields', [])
        for field in own_fields:
            fields_map[field['name']] = {'field': field, 'source': class_name}

        return list(fields_map.values())

    def _generate_random_data(self):
        """Generuje losowe dane dla aktualnie wybranej klasy."""
        selected_class = self.object_class_combo.currentText()
        if not selected_class:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy do generowania danych.")
            return

        # Generate random object name if empty
        if not self.object_name_input.text():
            random_name = f"obj_{''.join(random.choices(string.ascii_lowercase, k=5))}"
            self.object_name_input.setText(random_name)

        # Get all fields
        all_fields = self._get_all_fields_recursive(selected_class)

        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)

            if not label_item or not field_item:
                continue

            label_widget = label_item.widget()
            field_widget = field_item.widget()

            if not label_widget or not field_widget:
                continue

            label_text = label_widget.text()
            field_name = label_text.split('(')[0].strip()
            field_type = label_text.split('(')[1].split(')')[0].strip()

            # Generate random value based on type
            if isinstance(field_widget, QLineEdit):
                if field_type == "str":
                    field_widget.setText(''.join(random.choices(string.ascii_letters, k=10)))
                elif field_type == "int":
                    field_widget.setText(str(random.randint(0, 100)))
                elif field_type == "float":
                    field_widget.setText(f"{random.uniform(0, 100):.2f}")
                elif field_type in ["list", "dict"]:
                    field_widget.setText("[]" if field_type == "list" else "{}")
            elif isinstance(field_widget, QSpinBox):
                field_widget.setValue(random.randint(0, 100))
            elif isinstance(field_widget, QCheckBox):
                field_widget.setChecked(random.choice([True, False]))
            elif isinstance(field_widget, QComboBox):  # Composition
                if field_widget.count() > 1:  # Has options other than "(Brak)"
                    field_widget.setCurrentIndex(random.randint(1, field_widget.count() - 1))

    def _create_or_update_object(self):
        """Tworzy nowy obiekt lub aktualizuje istniejący."""
        class_name = self.object_class_combo.currentText()
        object_name = self.object_name_input.text().strip()

        if not class_name:
            QMessageBox.warning(self, "Błąd", "Nie wybrano klasy dla obiektu.")
            return

        if not object_name:
            QMessageBox.warning(self, "Błąd", "Nazwa obiektu nie może być pusta.")
            return

        # Collect attributes from form
        attributes = {}
        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)

            if not label_item or not field_item:
                continue

            label_widget = label_item.widget()
            field_widget = field_item.widget()

            if not label_widget or not field_widget:
                continue

            label_text = label_widget.text()
            field_name = label_text.split('(')[0].strip()
            field_type = label_text.split('(')[1].split(')')[0].strip()

            # Get value based on widget type
            if isinstance(field_widget, QLineEdit):
                value = field_widget.text()

                # Try to convert to proper type
                if field_type == "int":
                    try:
                        value = int(value) if value else 0
                    except ValueError:
                        QMessageBox.warning(self, "Błąd",
                                            f"Nieprawidłowa wartość dla pola {field_name}. Oczekiwano liczby całkowitej.")
                        return
                elif field_type == "float":
                    try:
                        value = float(value) if value else 0.0
                    except ValueError:
                        QMessageBox.warning(self, "Błąd",
                                            f"Nieprawidłowa wartość dla pola {field_name}. Oczekiwano liczby zmiennoprzecinkowej.")
                        return
                elif field_type in ["list", "dict"]:
                    value = [] if field_type == "list" else {}

            elif isinstance(field_widget, QSpinBox):
                value = field_widget.value()
            elif isinstance(field_widget, QCheckBox):
                value = field_widget.isChecked()
            elif isinstance(field_widget, QComboBox):  # Composition
                value = field_widget.currentText()
                if value == "(Brak)":
                    value = None

            attributes[field_name] = value

        # Create or update object
        self.objects[object_name] = {
            'class': class_name,
            'attributes': attributes
        }

        # Clear form and update UI
        self.object_name_input.clear()
        self.objects_changed.emit()
        QMessageBox.information(self, "Sukces",
                                f"Obiekt '{object_name}' został {'zaktualizowany' if object_name in self.objects else 'utworzony'}.")

    def _edit_selected_object(self):
        """Wczytuje zaznaczony obiekt do formularza do edycji."""
        selected_items = self.object_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Nie zaznaczono obiektu do edycji.")
            return

        # Find the top-level item (object name)
        item = selected_items[0]
        while item.parent():
            item = item.parent()

        object_name = item.text(0)
        if object_name not in self.objects:
            QMessageBox.warning(self, "Błąd", f"Nie znaleziono obiektu '{object_name}'.")
            return

        object_data = self.objects[object_name]

        # Load object data into form
        self.object_name_input.setText(object_name)
        class_index = self.object_class_combo.findText(object_data['class'])
        if class_index >= 0:
            self.object_class_combo.setCurrentIndex(class_index)

        # Wait for form to update
        QApplication.processEvents()

        # Fill attributes
        for i in range(self.object_fields_layout.rowCount()):
            label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)

            if not label_item or not field_item:
                continue

            label_widget = label_item.widget()
            field_widget = field_item.widget()

            if not label_widget or not field_widget:
                continue

            label_text = label_widget.text()
            field_name = label_text.split('(')[0].strip()

            if field_name not in object_data['attributes']:
                continue

            value = object_data['attributes'][field_name]

            if isinstance(field_widget, QLineEdit):
                field_widget.setText(str(value))
            elif isinstance(field_widget, QSpinBox):
                field_widget.setValue(int(value))
            elif isinstance(field_widget, QCheckBox):
                field_widget.setChecked(bool(value))
            elif isinstance(field_widget, QComboBox):  # Composition
                if value is None:
                    field_widget.setCurrentIndex(0)  # "(Brak)"
                else:
                    index = field_widget.findText(value)
                    if index >= 0:
                        field_widget.setCurrentIndex(index)

    def _delete_selected_object(self):
        """Usuwa zaznaczony obiekt."""
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
            return

        reply = QMessageBox.question(
            self, "Potwierdzenie",
            f"Czy na pewno chcesz usunąć obiekt '{object_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.objects[object_name]
            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces", f"Obiekt '{object_name}' został usunięty.")

    def _update_object_tree(self):
        """Aktualizuje drzewo obiektów."""
        self.object_tree.clear()

        for obj_name, obj_data in sorted(self.objects.items()):
            obj_item = QTreeWidgetItem([obj_name])
            font = obj_item.font(0)
            font.setBold(True)
            obj_item.setFont(0, font)
            self.object_tree.addTopLevelItem(obj_item)

            # Add class info
            class_item = QTreeWidgetItem(["Klasa", obj_data['class']])
            obj_item.addChild(class_item)

            # Add attributes
            if obj_data['attributes']:
                for attr_name, attr_value in sorted(obj_data['attributes'].items()):
                    attr_item = QTreeWidgetItem([attr_name, str(attr_value)])
                    obj_item.addChild(attr_item)
            else:
                no_attr_item = QTreeWidgetItem(["Brak atrybutów", ""])
                obj_item.addChild(no_attr_item)

        self.object_tree.expandAll()

    def _update_composition_combos(self):
        """Aktualizuje comboboxy dla relacji kompozycji."""
        for i in range(self.object_fields_layout.rowCount()):
            field_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not field_item:
                continue

            field_widget = field_item.widget()
            if isinstance(field_widget, QComboBox):
                current_value = field_widget.currentText()
                field_widget.clear()
                field_widget.addItem("(Brak)")

                # Get the field type from the label
                label_item = self.object_fields_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                if label_item and label_item.widget():
                    label_text = label_item.widget().text()
                    field_type = label_text.split('(')[1].split(')')[0].strip()

                    # Add compatible objects
                    for obj_name, obj_data in self.objects.items():
                        if obj_data['class'] == field_type:
                            field_widget.addItem(obj_name)

                # Restore selection
                index = field_widget.findText(current_value)
                if index >= 0:
                    field_widget.setCurrentIndex(index)

    def _export_to_json(self):
        """Eksportuje obiekty do pliku JSON."""
        if not self.objects:
            QMessageBox.warning(self, "Błąd", "Brak obiektów do eksportu.")
            return

        import json
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Eksport do JSON", "", "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.objects, f, indent=2)
                QMessageBox.information(self, "Sukces", f"Dane zostały wyeksportowane do {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać pliku: {str(e)}")

    def _export_to_python(self):
        """Eksportuje obiekty jako kod Pythona."""
        if not self.objects:
            QMessageBox.warning(self, "Błąd", "Brak obiektów do eksportu.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Eksport do Pythona", "", "Python Files (*.py);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write("# Wygenerowane obiekty\n\n")
                    for obj_name, obj_data in self.objects.items():
                        class_name = obj_data['class']
                        f.write(f"{obj_name} = {class_name}()\n")
                        for attr_name, attr_value in obj_data['attributes'].items():
                            if isinstance(attr_value, str):
                                attr_value = f"'{attr_value}'"
                            f.write(f"{obj_name}.{attr_name} = {attr_value}\n")
                        f.write("\n")
                QMessageBox.information(self, "Sukces", f"Kod Pythona został wyeksportowany do {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać pliku: {str(e)}")


if __name__ == "__main__":
    # Import system modules
    import sys
    import inspect
    from PyQt6.QtWidgets import QApplication

    # Import your class file - replace 'your_class_module' with the actual file name (without .py)
    import wygenerowany_kod

    # Dynamically build class dictionary from imported module
    example_classes = {}

    # Get all classes defined in the module
    for name, obj in inspect.getmembers(wygenerowany_kod):
        # Only include actual classes (not imported ones)
        if inspect.isclass(obj) and obj.__module__ == wygenerowany_kod.__name__:

            # Find parent class if there is inheritance
            parent = None
            for base in obj.__bases__:
                if base.__module__ == wygenerowany_kod.__name__ and base.__name__ != 'object':
                    parent = base.__name__
                    break

            # Get class fields from its __init__ parameters
            fields = []
            try:
                init_signature = inspect.signature(obj.__init__)
                for param_name, param in init_signature.parameters.items():
                    # Skip 'self' parameter
                    if param_name != 'self':
                        # Try to determine parameter type from annotations or defaults
                        param_type = "str"  # Default type
                        if param.annotation != inspect.Parameter.empty:
                            param_type = param.annotation.__name__
                        fields.append({"name": param_name, "type": param_type})
            except (ValueError, AttributeError):
                pass  # In case __init__ is not accessible or doesn't exist

            # Add to classes dictionary
            example_classes[name] = {
                "fields": fields,
                "inherits": parent,
                "compositions": []  # Would need more complex analysis for compositions
            }

    # Start the Object Generator App with our dynamically built classes

    app = QApplication(sys.argv)
    window = ObjectGeneratorApp(example_classes)
    window.show()
    sys.exit(app.exec())