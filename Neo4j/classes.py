from datetime import date, datetime, timedelta
from typing import List, Optional


class Node:
    def __init__(self):
        self.id = id(self)


class Person(Node):
    def __init__(self, name: str, birth_date: date):
        super().__init__()
        self.name = name
        self.birth_date = birth_date
        self.borrowed_books: List['Book'] = []

    def borrow_book(self, book: 'Book'):
        if book.is_available:
            book.is_available = False
            book.current_borrower = self
            self.borrowed_books.append(book)

    def return_book(self, book: 'Book'):
        if book in self.borrowed_books:
            book.is_available = True
            book.current_borrower = None
            self.borrowed_books.remove(book)


class Employee(Person):
    def __init__(self, name: str, birth_date: date, position: str):
        super().__init__(name, birth_date)
        self.position = position
        self.hire_date = datetime.now()


class Book(Node):
    def __init__(self, title: str, author: str, year: int, isbn: str, pages: int):
        super().__init__()
        self.title = title
        self.author = author
        self.year = year
        self.isbn = isbn
        self.pages = pages
        self.is_available = True
        self.current_borrower: Optional[Person] = None
        self.library: Optional['Library'] = None
        self.editor_comments = [
            ["Too slow", "Consider shortening"],
            ["Excellent pacing"],
            ["Revise dialogue", "Add emotional weight", ["Subcomment", "Another"]],
        ]
        # self.editor_comments = []



class EBook(Book):
    def __init__(self, title: str, author: str, year: int, isbn: str, pages: int, file_format: str):
        super().__init__(title, author, year, isbn, pages)
        self.file_format = file_format


class AudioBook(Book):
    def __init__(self, title: str, author: str, year: int, isbn: str, pages: int, duration_minutes: int):
        super().__init__(title, author, year, isbn, pages)
        self.duration_minutes = duration_minutes


class Library(Node):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.books: List[Book] = []
        self.people: List[Person] = []
        self.employees: List[Employee] = []

    def add_book(self, book: Book):
        book.library = self
        self.books.append(book)

    def add_person(self, person: Person):
        self.people.append(person)

    def add_employee(self, employee: Employee):
        self.employees.append(employee)
        self.add_person(employee)