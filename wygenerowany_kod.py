from typing import Any, Dict, List, Optional


# --- Class Definitions ---

class Nowa(object):
    def __init__(self, klasa: str):
        self.klasa = klasa
    pass # No objects defined

class Nowa2(Nowa):
    def __init__(self, klasa: str, klasa2: str):
        super().__init__(klasa)
        self.klasa2 = klasa2
    pass # No objects defined

class Nowa3(Nowa2):
    def __init__(self, klasa2: str, klasa3: str):
        super().__init__(klasa2)
        self.klasa3 = klasa3
    pass # No objects defined