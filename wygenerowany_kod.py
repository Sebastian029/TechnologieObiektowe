from typing import List, Set, FrozenSet

class Produkt:
    def __init__(self, nazwa: str, cena: float):
        self.nazwa = nazwa
        self.cena = cena

class Magazyn:
    def __init__(self):
        self.produkty: List[Produkt] = []


