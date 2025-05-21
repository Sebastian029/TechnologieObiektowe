from typing import List



class Klasa4:
    def __init__(self, pole4: str):
        self.pole4: str = pole4

class Klasa1:
    def __init__(self, pole1: str, composed_klasa4_1: 'Klasa4'):
        self.pole1: str = pole1
        self.composed_klasa4_1: 'Klasa4' = composed_klasa4_1

class Klasa2:
    def __init__(self, pole2: str):
        self.pole2: str = pole2

class Klasa3:
    def __init__(self, pole3: str, cos2: List[Klasa2]):
        self.pole3: str = pole3
        self.cos2: List[Klasa2] = cos2