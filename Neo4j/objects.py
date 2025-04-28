from datetime import date
from classes import *

# Create books (subclass examples)
# book1 = Book("Wiedźmin", "Andrzej Sapkowski", 1990, "1234567890", 320)
# ebook1 = EBook("Python 101", "John Doe", 2020, "0987654321", 200, "PDF")
# audiobook1 = AudioBook("Dune", "Frank Herbert", 1965, "1122334455", 600, 720)
#
# # Create people
# person1 = Person("Jan Kowalski", date(1990, 5, 20))
# person2 = Person("Anna Nowak", date(1985, 7, 14))
#
# # Person borrows books
# person1.borrow_book(book1)
# person2.borrow_book(ebook1)
#
# # Create employee (inherits from Person)
# employee1 = Employee("Magdalena Nowak", date(1991, 4, 2), "Librarian")
#
# # Create library
# library = Library("City Library")
# library.add_book(book1)
# library.add_book(ebook1)
# library.add_book(audiobook1)
# library.add_person(person1)
# library.add_person(person2)
# library.add_employee(employee1)
#
# # Add another library and book for diversity
# library2 = Library("Community Library")
# book2 = Book("Clean Code", "Robert C. Martin", 2008, "5566778899", 464)
# library2.add_book(book2)
#
# # Create another person and borrow book from 2nd library
# person3 = Person("Tomasz Zięba", date(1993, 3, 3))
# person3.borrow_book(book2)
# library2.add_person(person3)
#
# # Final list for Neo4j conversion
# objects_list = [library, library2]
objects_list = [Dog("Burek", "Labrador")]