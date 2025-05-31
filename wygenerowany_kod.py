
class Klasa:
    def __init__(self, aaa: str, dddd: int):
        self.aaa: str = aaa
        self.dddd: int = dddd

class Klasa2:
    def __init__(self, aaaa_aaa: str, aaaa_dddd: int):
        self.aaaa: Klasa = Klasa(aaaa_aaa, aaaa_dddd)