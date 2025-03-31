import inspect
from datetime import date, datetime, timedelta    

def analyze_object(self, obj, depth=0, visited=None):
        if visited is None:
            visited = set()

        if id(obj) in visited:
            return
        visited.add(id(obj))

        indent = "  " * depth

        if isinstance(obj, (int, float, complex, str, bool, type(None), date, datetime)):
            print(f"{indent}{repr(obj)} ({type(obj).__name__})")
            return
        elif isinstance(obj, (list, tuple, set, frozenset)):
            print(f"{indent}{type(obj).__name__} [{len(obj)}]:")
            for item in obj:
                self.analyze_object(item, depth + 1, visited)
        elif isinstance(obj, dict):
            print(f"{indent}Dict [{len(obj)}]:")
            for key, value in obj.items():
                print(f"{indent}  Key: {repr(key)}")
                self.analyze_object(value, depth + 1, visited)
        elif inspect.isclass(obj):
            print(f"{indent}Class {obj.__name__}")
        elif hasattr(obj, "__dict__"):
            print(f"{indent}Object of {type(obj).__name__}:")
            for attr, value in vars(obj).items():
                print(f"{indent}  {attr}:")
                self.analyze_object(value, depth + 1, visited)
        else:
            print(f"{indent}Unknown Type: {repr(obj)} ({type(obj).__name__})")