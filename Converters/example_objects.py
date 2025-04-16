from example_classes import *

library = LibraryManagementSystem("Centralna Biblioteka")

employee = Employee("Jan Kowalski", "jan.kowalski@biblioteka.pl", "90010112345", 5000.0, "Kierownik Działu")
library.hire_employee(employee)

python_book = Book("Python dla zaawansowanych", "9788328323468", ["Mateusz Dąbrowski"], 450)
python_book.add_genre("Informatyka")

ebook = EBook("Machine Learning w Pythonie", "9788328323475", ["Anna Nowak"], 12.5, "EPUB")
audiobook = AudioBook("Historia Świata", "9788328323482", ["Piotr Kowalczyk"], timedelta(hours=8), "Krzysztof Baranowski")

library.add_book(python_book)
library.add_book(ebook)
library.add_book(audiobook)

magdalena = Person("Magdalena Nowak", "magdalena.nowak@example.com", "95070112345")
magdalena1 = Person("Magdalena 123", "magdalena.nowak@example.com", "95070112345")
magdalena2 = Person("Magdalena QWE", "magdalena.nowak@example.com", "95070112345")
magdalena.borrow_book(python_book, library)
magdalena1.borrow_book(python_book, library)
magdalena2.borrow_book(python_book, library)

objects_list = [ library, employee, python_book, ebook, audiobook, magdalena]