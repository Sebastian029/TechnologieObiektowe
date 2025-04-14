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
import importlib
import inspect

# Reusing types from the original program
ClassData = Dict[str, Any]
ClassesDict = Dict[str, ClassData]
ObjectData = Dict[str, Any]
ObjectsDict = Dict[str, Any]  # Changed to store actual objects


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

        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and obj.__module__ == module.__name__:
                # Find parent class if there is inheritance
                parent = None
                for base in obj.__bases__:
                    if base.__module__ == module.__name__ and base.__name__ != 'object':
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
                                if hasattr(param.annotation, '__name__'):
                                    param_type = param.annotation.__name__
                                else:
                                    param_type = str(param.annotation)
                            fields.append({"name": param_name, "type": param_type})
                except (ValueError, AttributeError):
                    pass  # In case __init__ is not accessible or doesn't exist

                # Add to classes dictionary
                classes[name] = {
                    "fields": fields,
                    "inherits": parent,
                    "class_obj": obj  # Store the actual class object
                }

        return classes

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

        # Add button for creating predefined objects
        self.create_predefined_btn = QPushButton("Utwórz przykładowe obiekty")
        self.create_predefined_btn.clicked.connect(self._create_predefined_objects)
        left_layout.addWidget(self.create_predefined_btn)

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

        self.create_object_btn = QPushButton("MongoDb")
        self.create_object_btn.clicked.connect(self._create_selected_object)
        btn_layout.addWidget(self.create_object_btn)

        self.delete_object_btn = QPushButton("Usuń zaznaczony")
        self.delete_object_btn.clicked.connect(self._delete_selected_object)
        btn_layout.addWidget(self.delete_object_btn)
        right_layout.addLayout(btn_layout)

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
                for obj_name, obj_data in self.object_data.items():
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

    def _create_predefined_objects(self):
        """Creates predefined objects that can be accessed normally."""
        try:
            # Example: Create some Book and Library objects
            book1 = self.classes['Book']['class_obj'](pages=200)
            self.objects['book1'] = book1
            self.object_data['book1'] = {
                'class': 'Book',
                'attributes': {'pages': 200}
            }

            book2 = self.classes['Book']['class_obj'](pages=350)
            self.objects['book2'] = book2
            self.object_data['book2'] = {
                'class': 'Book',
                'attributes': {'pages': 350}
            }

            library1 = self.classes['Library']['class_obj'](book_obj=book1, city="Warsaw")
            self.objects['library1'] = library1
            self.object_data['library1'] = {
                'class': 'Library',
                'attributes': {
                    'book_obj': book1,
                    'city': "Warsaw"
                }
            }

            library2 = self.classes['Library']['class_obj'](book_obj=book2, city="Krakow")
            self.objects['library2'] = library2
            self.object_data['library2'] = {
                'class': 'Library',
                'attributes': {
                    'book_obj': book2,
                    'city': "Krakow"
                }
            }

            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces", "Utworzono przykładowe obiekty: book1, book2, library1, library2")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć przykładowych obiektów: {str(e)}")

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
                else:
                    # Get the actual object reference
                    value = self.objects.get(value)

            attributes[field_name] = value

        # Create or update the actual Python object
        try:
            if object_name in self.objects:
                # Update existing object
                obj = self.objects[object_name]
                for attr_name, attr_value in attributes.items():
                    setattr(obj, attr_name, attr_value)
            else:
                # Create new object
                class_obj = self.classes[class_name]['class_obj']

                # Prepare constructor arguments
                constructor_args = {}
                for field_info in self._get_all_fields_recursive(class_name):
                    field_name = field_info['field']['name']
                    if field_name in attributes:
                        constructor_args[field_name] = attributes[field_name]

                # Create the instance
                obj = class_obj(**constructor_args)
                self.objects[object_name] = obj

            # Update metadata
            self.object_data[object_name] = {
                'class': class_name,
                'attributes': attributes
            }

            # Clear form and update UI
            self.object_name_input.clear()
            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces",
                                    f"Obiekt '{object_name}' został {'zaktualizowany' if object_name in self.objects else 'utworzony'}.")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć obiektu: {str(e)}")

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

        object_metadata = self.object_data[object_name]

        # Load object data into form
        self.object_name_input.setText(object_name)
        class_index = self.object_class_combo.findText(object_metadata['class'])
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

            if field_name not in object_metadata['attributes']:
                continue

            value = object_metadata['attributes'][field_name]

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
                    # Find the object name for this reference
                    found = False
                    for obj_name, obj in self.objects.items():
                        if obj is value:
                            index = field_widget.findText(obj_name)
                            if index >= 0:
                                field_widget.setCurrentIndex(index)
                                found = True
                                break
                    if not found:
                        field_widget.setCurrentIndex(0)

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
            del self.object_data[object_name]
            self.objects_changed.emit()
            QMessageBox.information(self, "Sukces", f"Obiekt '{object_name}' został usunięty.")

    def _create_selected_object(self):
        """Save selected objects to MongoDB"""
        try:
            from MongoDB.main import PyMongoConverter
            converter = PyMongoConverter(
                connection_string="mongodb://localhost:27017/",
                db_name="object_db"
            )

            try:
                # Save all objects with their names
                for obj_name, obj in self.objects.items():
                    print(f"Saving {obj_name} ({obj.__class__.__name__}) to MongoDB...")
                    # Save with object name as document ID
                    converter.save_to_mongodb(obj, document_id=obj_name)

                QMessageBox.information(self, "Success", "Objects saved to MongoDB successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save objects to MongoDB: {str(e)}")
            finally:
                converter.close()
        except ImportError as e :
            QMessageBox.critical(self, "Error", f"Could not import PyMongoConverter {e}")

    def _update_object_tree(self):
        """Aktualizuje drzewo obiektów."""
        self.object_tree.clear()

        for obj_name, obj_metadata in sorted(self.object_data.items()):
            obj_item = QTreeWidgetItem([obj_name])
            font = obj_item.font(0)
            font.setBold(True)
            obj_item.setFont(0, font)
            self.object_tree.addTopLevelItem(obj_item)

            # Add class info
            class_item = QTreeWidgetItem(["Klasa", obj_metadata['class']])
            obj_item.addChild(class_item)

            # Get the actual object
            obj = self.objects.get(obj_name)

            # Add attributes
            if obj_metadata['attributes']:
                for attr_name in sorted(obj_metadata['attributes'].keys()):
                    try:
                        attr_value = getattr(obj, attr_name, "<not set>")
                        attr_item = QTreeWidgetItem([attr_name, str(attr_value)])
                        obj_item.addChild(attr_item)
                    except Exception as e:
                        attr_item = QTreeWidgetItem([attr_name, f"<error: {str(e)}>"])
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
                    for obj_name, obj_metadata in self.object_data.items():
                        if obj_metadata['class'] == field_type:
                            field_widget.addItem(obj_name)

                # Restore selection
                index = field_widget.findText(current_value)
                if index >= 0:
                    field_widget.setCurrentIndex(index)


if __name__ == "__main__":
    # Import the module with class definitions
    import wygenerowany_kod

    app = QApplication(sys.argv)
    window = ObjectGeneratorApp(wygenerowany_kod)
    window.show()
    sys.exit(app.exec())