from typing import Dict, FrozenSet, List, Set, Tuple



class Wielka:
    def __init__(self, ddd: Set[str]):
        self.ddd: Set[str] = ddd

class Klasa(Wielka):
    def __init__(self, ddd: Set[str], sss: Set[str]):
        super().__init__(ddd)
        self.sss: Set[str] = sss