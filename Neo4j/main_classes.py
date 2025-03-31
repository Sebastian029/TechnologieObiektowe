from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import List, Dict, Set, Optional, Union

import object_reader as object_reader




class Person:
    def __init__(self, name: str, email: str, pesel: str):
        self.name = name
        self.email = email
        self.pesel = pesel
        self.borrowed_books: List[Book] = []

    def borrow_book(self, book: 'Book', library: 'LibraryManagementSystem') -> bool:
        if library.borrow_book(book, self):
            self.borrowed_books.append(book)
            return True
        return False

    def return_book(self, book: 'Book', library: 'LibraryManagementSystem') -> bool:
        if book in self.borrowed_books:
            library.return_book(book, self)
            self.borrowed_books.remove(book)
            return True
        return False


class Employee(Person):
    def __init__(self, name: str, email: str, pesel: str, salary: float, position: str):
        super().__init__(name, email, pesel)
        self.salary = salary
        self.position = position
        self.hire_date = datetime.now()


class Document(ABC):
    def __init__(self, title: str, unique_id: str):
        self.title = title
        self.unique_id = unique_id
        self.creation_date = datetime.now()

    @abstractmethod
    def get_summary(self) -> str:
        pass


class Book(Document):
    def __init__(self, title: str, isbn: str, authors: List[str], pages: int):
        super().__init__(title, isbn)
        self.isbn = self.unique_id
        self.authors = authors
        self.pages = pages
        self.genres: Set[str] = set()
        self.is_available: bool = True
        self.current_borrower: Optional[Person] = None

    def get_summary(self) -> str:
        availability = "Dostępna" if self.is_available else "Wypożyczona"
        return f"Książka: {self.title} ({self.pages} stron) - {availability}"

    def add_genre(self, genre: str):
        self.genres.add(genre)


class EBook(Book):
    def __init__(self, title: str, isbn: str, authors: List[str], file_size: float, format: str):
        super().__init__(title, isbn, authors, 0)
        self.file_size = file_size
        self.format = format

    def get_summary(self) -> str:
        availability = "Dostępna" if self.is_available else "Wypożyczona"
        return f"E-Book: {self.title} ({self.format}, {self.file_size} MB) - {availability}"


class AudioBook(Book):
    def __init__(self, title: str, isbn: str, authors: List[str], duration: timedelta, narrator: str):
        super().__init__(title, isbn, authors, 0)
        self.duration = duration
        self.narrator = narrator

    def get_summary(self) -> str:
        availability = "Dostępna" if self.is_available else "Wypożyczona"
        return f"Audiobook: {self.title} (narrator: {self.narrator}, {self.duration}) - {availability}"


class LibraryManagementSystem:
    def __init__(self, name: str):
        self.name = name
        self.books: Dict[str, Book] = {}
        self.employees: List[Employee] = []
        self.borrowing_history: Dict[str, List[Book]] = {}

    def add_book(self, book: Book):
        self.books[book.isbn] = book

    def hire_employee(self, employee: Employee):
        self.employees.append(employee)

    def borrow_book(self, book: Book, borrower: Person) -> bool:
        if book.isbn in self.books and book.is_available:
            book.is_available = False
            book.current_borrower = borrower

            if borrower.name not in self.borrowing_history:
                self.borrowing_history[borrower.name] = []
            self.borrowing_history[borrower.name].append(book)

            return True
        return False

    def return_book(self, book: Book, borrower: Person):
        if book.current_borrower == borrower:
            book.is_available = True
            book.current_borrower = None


def main():
    library = LibraryManagementSystem("Centralna Biblioteka")

    library.hire_employee(Employee(
        "Jan Kowalski",
        "jan.kowalski@biblioteka.pl",
        "90010112345",
        5000.0,
        "Kierownik Działu"
    ))

    python_book = Book(
        "Python dla zaawansowanych",
        "9788328323468",
        ["Mateusz Dąbrowski"],
        450
    )
    python_book.add_genre("Informatyka")

    ebook = EBook(
        "Machine Learning w Pythonie",
        "9788328323475",
        ["Anna Nowak"],
        12.5,
        "EPUB"
    )

    audiobook = AudioBook(
        "Historia Świata",
        "9788328323482",
        ["Piotr Kowalczyk"],
        timedelta(hours=8),
        "Krzysztof Baranowski"
    )

    library.add_book(python_book)
    library.add_book(ebook)
    library.add_book(audiobook)

    magdalena = Person(
        "Magdalena Nowak",
        "magdalena.nowak@example.com",
        "95070112345"
    )

    magdalena.borrow_book(python_book, library)

    # print(f"Biblioteka: {library.name}")
    # print(f"Liczba książek: {len(library.books)}")
    # print(f"Liczba pracowników: {len(library.employees)}")
    # print(f"Książki {magdalena.name}: {[book.title for book in magdalena.borrowed_books]}")
    # print("\nPodsumowanie książek:")
    # for book in library.books.values():
    #     print(book.get_summary())
    object_reader.analyze_object(ebook)

if __name__ == "__main__":
    main()


