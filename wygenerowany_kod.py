from __future__ import annotations
from typing import Dict, List, Set, Tuple, FrozenSet

class Klasa:
    def __init__(self, pole1: str, pole2: int, pole3: float, pole4: bool, pole5: complex):
        self.pole1: str = pole1
        self.pole2: int = pole2
        self.pole3: float = pole3
        self.pole4: bool = pole4
        self.pole5: complex = pole5

class Klasa2(Klasa):
    def __init__(self, pole1: str, pole2: int, pole3: float, pole4: bool, pole5: complex, nazwa: str):
        super().__init__(pole1, pole2, pole3, pole4, pole5)
        self.nazwa: str = nazwa

class Magazyn:
    def __init__(self, mag1: List[Produkt] = None, mag2: Dict[str, Produkt] = None, mag3: Tuple[Produkt, ...] = None, mag4: FrozenSet[Produkt] = None, mag5: Set[Produkt] = None):
        self.mag1 = mag1 if mag1 is not None else []
        self.mag2 = mag2 if mag2 is not None else {}
        self.mag3 = mag3 if mag3 is not None else tuple()
        self.mag4 = mag4 if mag4 is not None else frozenset()
        self.mag5 = mag5 if mag5 is not None else set()

class Produkt:
    def __init__(self, cena: float, nazwa: str):
        self.cena: float = cena
        self.nazwa: str = nazwa

    def __eq__(self, other):
        if not isinstance(other, Produkt):
            return NotImplemented
        return (self.cena, self.nazwa,) == (other.cena, other.nazwa,)

    def __hash__(self):
        return hash((self.cena, self.nazwa,))