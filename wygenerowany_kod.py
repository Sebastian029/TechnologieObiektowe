from typing import Any, Dict, List, Optional



class K1:
    def __init__(self, p1: str, p11: str, k2_obj: Optional['K2'] = None):
        self.k2_obj = k2_obj
        self.p1 = p1
        self.p11 = p11

class K2(K1):
    def __init__(self, k2_obj: 'K2', p1: str, p11: str, p2: str):
        super().__init__(p1, p11)
        self.p2 = p2

class K4(K1):
    def __init__(self, k2_obj: 'K2', p1: str, p11: str, p4: str):
        super().__init__(p1, p11)
        self.p4 = p4

class K3(K2):
    def __init__(self, k2_obj: 'K2', p1: str, p11: str, p2: str, p3: str):
        super().__init__(p1, p11, p2)
        self.p3 = p3