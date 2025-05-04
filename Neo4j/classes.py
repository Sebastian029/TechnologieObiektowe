from datetime import date, datetime, timedelta
from typing import List, Optional

# class Animal:
#     def __init__(self, name):
#         self.name = name

# class Dog(Animal):
#     def __init__(self, name, breed):
#         super().__init__(name)
#         self.breed = breed


class Pies:
    def __init__(self, imie, rasa):
        self.imie = imie
        self.rasa = rasa
        
class SzkolkaDlaPsow:
    def __init__(self):
        self.nazwa = "Szkoła dla psów"
        self.psy = []  
        
    def dodaj_psa(self, pies):
        self.psy.append(pies)
        print(f"Dodano psa: {pies.imie} ({pies.rasa})")