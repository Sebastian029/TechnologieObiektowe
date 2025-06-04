from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple, FrozenSet

class Cos:
    def __init__(self, nowa: str):
        self.nowa: str = nowa

class Produkt(Cos):

    def __eq__(self, other):
        if not isinstance(other, Produkt):
            return NotImplemented
        return (self.cena,) == (other.cena,)

    def __hash__(self):
        return hash((self.cena,))
    def __init__(self, nowa: str, cena: int):
        super().__init__(nowa)
        self.nowa = nowa
        self.cena: int = cena

class Magazyn:
    def __init__(self, mag1: List[Produkt] = None, mag2: Dict[str, Produkt] = None, mag3: Tuple[Produkt, ...] = None, mag4: FrozenSet[Produkt] = None, mag5: Set[Produkt] = None):
        self.mag1 = mag1 if mag1 is not None else []
        self.mag2 = mag2 if mag2 is not None else {}
        self.mag3 = mag3 if mag3 is not None else tuple()
        self.mag4 = mag4 if mag4 is not None else frozenset()
        self.mag5 = mag5 if mag5 is not None else set()