from typing import Any, Dict, List, Optional



class Klasa:
    def __init__(self, nowa: str):
        self.nowa = nowa

class Klasa2:
    def __init__(self, stara: str, composed_klasa_1: Optional['Klasa'] = None):
        self.composed_klasa_1 = composed_klasa_1
        self.stara = stara