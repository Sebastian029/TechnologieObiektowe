from datetime import date, datetime, timedelta
from typing import List, Optional



class Book:
    def __init__(self, title: str):
        self.title = title


class Library:
    def __init__(self, name: str, book:Book):
        super().__init__()
        self.name = name
        self.book: Book = book
