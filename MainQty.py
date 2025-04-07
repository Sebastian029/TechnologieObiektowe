import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout

class SimpleApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Prosty interfejs PyQt6")
        
        self.layout = QVBoxLayout()
        
        self.label = QLabel("Wpisz coś:")
        self.layout.addWidget(self.label)
        
        self.text_input = QLineEdit()
        self.text_input.setFixedSize(200, 30)  # Stałe parametry pola tekstowego
        
        text_layout = QHBoxLayout()
        text_layout.addWidget(self.text_input)
        text_layout.addStretch()
        
        self.layout.addLayout(text_layout)
        
        self.button = QPushButton("Pokaż tekst")
        self.button.clicked.connect(self.show_text)
        self.layout.addWidget(self.button)
        
        self.result_label = QLabel("")
        self.layout.addWidget(self.result_label)
        
        self.setLayout(self.layout)
    
    def show_text(self):
        self.result_label.setText(self.text_input.text())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimpleApp()
    window.show()
    sys.exit(app.exec())