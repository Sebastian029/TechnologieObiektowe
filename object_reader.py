import inspect
from datetime import date, datetime, timedelta

def analyze_object(obj, depth=0, visited=None):
    if visited is None:
        visited = set()

    if id(obj) in visited:
        return
    visited.add(id(obj))

    indent = "  " * depth

    # basic types
    if isinstance(obj, (int, float, complex, str, bool, type(None), date, datetime)):
        print(f"{indent}{repr(obj)} ({type(obj).__name__})")
        return

    # iter collections
    elif isinstance(obj, (list, tuple, set, frozenset)):
        print(f"{indent}{type(obj).__name__} [{len(obj)}]:")
        for item in obj:
            analyze_object(item, depth + 1, visited)

    # dictionary
    elif isinstance(obj, dict):
        print(f"{indent}Dict [{len(obj)}]:")
        for key, value in obj.items():
            print(f"{indent}  Key: {repr(key)}")
            analyze_object(value, depth + 1, visited)

    # class
    elif inspect.isclass(obj):
        # Sprawdzenie, czy to klasa
        print(f"{indent}Class {obj.__name__}")

    # class attributes
    elif hasattr(obj, "__dict__"):
        print(f"{indent}Object of {type(obj).__name__}:")
        for attr, value in vars(obj).items():
            print(f"{indent}  {attr}:")
            analyze_object(value, depth + 1, visited)

    else:
        print(f"{indent}Unknown Type: {repr(obj)} ({type(obj).__name__})")