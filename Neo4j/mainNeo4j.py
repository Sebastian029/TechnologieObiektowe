import inspect
from datetime import date, datetime
from neo4j import GraphDatabase
# Assuming your classes (Node, Person, Employee, Book, EBook, AudioBook, Library)
# are in a file named 'classes.py'
from classes import Node, Person, Employee, Book, EBook, AudioBook, Library
# Assuming your data setup (book1, person1, library, etc.)
# and objects_list are in a file named 'data_setup.py'
from objects import objects_list

class Neo4jConverter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        # Cache for nodes created *within a single top-level save* operation
        # Maps Python object id() to Neo4j elementId
        self._saved_nodes_cache = {}

    def close(self):
        self.driver.close()

    def _clear_database(self):
        """Utility function to clear the database before saving (optional)."""
        print("Clearing database...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("Database cleared.")

    def _serialize_value(self, value):
        """Serializes basic Python types into Neo4j-compatible property values."""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        elif isinstance(value, (date, datetime)):
            # Neo4j supports native Date and DateTime types
            return value
        elif isinstance(value, complex):
            # Convert complex numbers to string representation
            return str(value)
        # --- Removed serialization for list/tuple/set/dict ---
        # These are now handled by relationship creation logic if they contain objects
        # If they contain only basic types, Neo4j can store them directly as list properties
        # For simplicity here, we only handle basic scalar types as properties.
        # Complex structures containing only basic types could be added here if needed.
        return str(value) # Fallback for other unforeseen types

    def _is_basic_type(self, val):
        """Checks if a value is a basic type suitable for a node property."""
        # Allow lists/tuples/sets containing ONLY basic types as properties
        if isinstance(val, (list, tuple, set)):
            return all(self._is_basic_type(item) for item in val)
        # Allow dicts containing ONLY basic types as values (keys must be strings)
        if isinstance(val, dict):
             return all(isinstance(k, str) and self._is_basic_type(v) for k, v in val.items())

        # Handle standard basic types including date/datetime
        return isinstance(val, (str, int, float, bool, type(None), datetime, date))

    def _get_node_labels(self, obj):
        """Gets all class names in the object's inheritance hierarchy (up to Node/object)."""
        labels = []
        # Use inspect.getmro to get the Method Resolution Order (inheritance)
        for cls in inspect.getmro(obj.__class__):
            if cls is object:  # Stop at the base 'object' class
                continue
            # Optional: Stop at your custom base class like 'Node' if desired
            # if cls is Node:
            #     labels.append(cls.__name__)
            #     break
            labels.append(cls.__name__)
        return ":".join(labels) # Format for Cypher (e.g., "Employee:Person:Node")

    def _get_or_create_node(self, obj, session):
        """
        Gets the elementId of an existing node from the cache or creates a new node
        in Neo4j if it doesn't exist in the current session's cache.
        Uses MERGE based on a unique property (id if available, otherwise relies on cache).
        """
        obj_py_id = id(obj)
        if obj_py_id in self._saved_nodes_cache:
            return self._saved_nodes_cache[obj_py_id]

        labels = self._get_node_labels(obj)
        properties = {}
        # Use a potentially unique identifier if the object has one (like 'isbn' or 'id')
        # Here, we fall back to using the Python id() for cache lookup, but don't store it as a property.
        # In a real scenario, you'd MERGE on a meaningful business key.
        unique_prop_key = None
        unique_prop_val = None
        if hasattr(obj, 'isbn'): # Example: Use ISBN for Books
             unique_prop_key = 'isbn'
             unique_prop_val = getattr(obj, 'isbn')
        elif hasattr(obj, 'name') and isinstance(obj, (Person, Library)): # Example: Use name for Person/Library
             unique_prop_key = 'name'
             unique_prop_val = getattr(obj, 'name')
        # Add more conditions for other classes with unique identifiers

        for attr, value in vars(obj).items():
             # Only store basic types or lists/dicts of basic types as properties
            if self._is_basic_type(value):
                 # Skip the unique property if we are using it for MERGE below
                if attr == unique_prop_key:
                    continue
                properties[attr] = self._serialize_value(value)

        # Use MERGE to avoid creating duplicate nodes based on a unique property if available
        if unique_prop_key:
            prop_set_clause = ", ".join(f"n.{k} = ${k}" for k in properties)
            # Add the unique property to the parameters for the SET clause too
            properties[unique_prop_key] = unique_prop_val
            query = f"""
            MERGE (n:{labels} {{{unique_prop_key}: ${unique_prop_key}}})
            ON CREATE SET {prop_set_clause}
            ON MATCH SET {prop_set_clause}
            RETURN elementId(n)
            """
            # Pass all properties (unique + others) as parameters
            params = {unique_prop_key: unique_prop_val, **properties}

        else:
            # If no unique business key, create based on labels and properties (less robust for merging later)
            # This relies heavily on the _saved_nodes_cache to prevent duplicates *within this run*
            prop_keys_values = ", ".join(f"{k}: ${k}" for k in properties)
            query = f"CREATE (n:{labels} {{{prop_keys_values}}}) RETURN elementId(n)"
            params = properties


        # --- Debugging print ---
        # print(f"  Running Query: {query}")
        # print(f"  With Params: {params}")
        # --- End Debugging ---

        try:
            result = session.run(query, **params)
            element_id = result.single()[0]
            self._saved_nodes_cache[obj_py_id] = element_id
            # print(f"  Created/Merged Node: {labels} (ElementID: {element_id})") # Debug
            return element_id
        except Exception as e:
            print(f"  Error running query: {query}")
            print(f"  Params: {params}")
            print(f"  Error: {e}")
            # Handle error appropriately - maybe raise it, maybe log and continue
            raise # Re-raise the exception to stop execution

    def _create_relationship(self, from_element_id, to_element_id, rel_type, session):
        """Creates a relationship between two nodes using their elementIds."""
        if not from_element_id or not to_element_id:
            print(f"  Skipping relationship: Invalid elementId (From: {from_element_id}, To: {to_element_id})")
            return

        # Sanitize relationship type (Neo4j doesn't like spaces or special chars)
        rel_type = ''.join(c if c.isalnum() else '_' for c in rel_type).upper()
        if not rel_type: # Handle cases where attribute name was weird
            rel_type = "RELATED_TO"

        query = f"""
        MATCH (a) WHERE elementId(a) = $from_id
        MATCH (b) WHERE elementId(b) = $to_id
        MERGE (a)-[r:{rel_type}]->(b)
        """
        # print(f"  Creating Relationship: ({from_element_id})-[{rel_type}]->({to_element_id})") # Debug
        session.run(query, from_id=from_element_id, to_id=to_element_id)

    def save_object_graph(self, start_obj):
        """Saves a graph of objects starting from start_obj."""
        self._saved_nodes_cache = {}  # Clear cache for this save operation
        visited_in_session = set() # Track objects visited in this specific call to prevent infinite loops

        with self.driver.session() as session:
            self._recursive_save_internal(start_obj, session, visited_in_session)

    def _recursive_save_internal(self, obj, session, visited_in_session):
        """Internal recursive function to traverse and save objects."""
        if obj is None or self._is_basic_type(obj):
             # Don't try to save basic types as separate nodes
             # print(f"Skipping basic type: {type(obj)}") # Debug
            return

        obj_py_id = id(obj)
        if obj_py_id in visited_in_session:
            # Already processed in this current traversal path, break potential cycle
            # print(f"Already visited in this session: {obj.__class__.__name__} ({obj_py_id})") # Debug
            return

        visited_in_session.add(obj_py_id)
        # print(f"Processing: {obj.__class__.__name__} ({obj_py_id})") # Debug

        # Ensure the current node exists (or create it)
        current_element_id = self._get_or_create_node(obj, session)
        if not current_element_id:
             print(f"Error: Failed to get or create node for {obj.__class__.__name__}")
             visited_in_session.remove(obj_py_id) # Allow revisiting if creation failed? Maybe not.
             return # Stop processing this branch if node creation failed


        # Iterate through attributes to find relationships
        for attr, value in vars(obj).items():
            if self._is_basic_type(value):
                # Basic types are handled as properties in _get_or_create_node
                continue

            # Determine relationship type (default to attribute name)
            rel_type = attr.upper()
            # --- Add specific relationship naming overrides here if desired ---
            # Example: if attr == 'borrowed_books': rel_type = 'HAS_BORROWED'
            # Example: if attr == 'current_borrower': rel_type = 'BORROWED_BY'
            # Example: if attr == 'library' and isinstance(obj, Book): rel_type = 'BELONGS_TO'
            # Example: if attr == 'books' and isinstance(obj, Library): rel_type = 'CONTAINS_BOOK'
            # Example: if attr == 'people' and isinstance(obj, Library): rel_type = 'HAS_MEMBER'
            # Example: if attr == 'employees' and isinstance(obj, Library): rel_type = 'EMPLOYS'
            # For now, we stick to the simple attr.upper() for demonstration
            # -----------------------------------------------------------------


            if isinstance(value, (list, set, tuple)):
                # Handle collections of objects
                for item in value:
                    if not self._is_basic_type(item) and item is not None:
                        # Recursively save the related object
                        self._recursive_save_internal(item, session, visited_in_session)
                        # Get the related object's elementId (should be in cache now)
                        related_element_id = self._saved_nodes_cache.get(id(item))
                        # Create the relationship
                        if related_element_id:
                             self._create_relationship(current_element_id, related_element_id, rel_type, session)
                        else:
                             print(f"Warning: Could not find elementId for item in list/set/tuple attribute '{attr}' of {obj.__class__.__name__}")

            elif isinstance(value, dict):
                 # Handle dictionaries where values might be objects
                 # Relationships typically go to the values. Keys could be properties on the relationship if needed.
                for key, item in value.items():
                     if not self._is_basic_type(item) and item is not None:
                        # Recursively save the related object
                        self._recursive_save_internal(item, session, visited_in_session)
                        # Get the related object's elementId
                        related_element_id = self._saved_nodes_cache.get(id(item))
                        # Create the relationship
                        if related_element_id:
                             # You could add the 'key' as a property on the relationship here if needed
                            self._create_relationship(current_element_id, related_element_id, rel_type, session)
                        else:
                             print(f"Warning: Could not find elementId for item in dict attribute '{attr}' of {obj.__class__.__name__}")

            elif hasattr(value, "__dict__"): # Check if it's a custom object instance
                 # Handle direct references to other objects
                 # Recursively save the related object
                self._recursive_save_internal(value, session, visited_in_session)
                 # Get the related object's elementId
                related_element_id = self._saved_nodes_cache.get(id(value))
                 # Create the relationship
                if related_element_id:
                     self._create_relationship(current_element_id, related_element_id, rel_type, session)
                else:
                      print(f"Warning: Could not find elementId for object attribute '{attr}' of {obj.__class__.__name__}")

            # else: Other types (like functions, classes) are ignored for relationship creation

        # Remove from visited_in_session *after* processing children to allow different paths to reach this node
        # visited_in_session.remove(obj_py_id) # Keep commented - prevents revisiting entirely in one save call


if __name__ == "__main__":
    # Make sure Neo4j Desktop or server is running!
    # Replace with your actual Neo4j connection details
    converter = Neo4jConverter(uri="bolt://localhost:7687", user="neo4j", password="password") # Replace password

    try:
        # Optional: Clear database before running the script each time
        converter._clear_database()

        # Process each top-level object in the list
        # The converter will handle duplicates and shared objects across these top-level calls
        # because the _saved_nodes_cache persists *within* a single save_object_graph call,
        # and MERGE is used in the database.
        print("Starting Neo4j conversion...")
        for start_object in objects_list:
            print(f"\nSaving graph starting from: {start_object.__class__.__name__} (Name: {getattr(start_object, 'name', 'N/A')})")
            converter.save_object_graph(start_object)

        print("\n--------------------")
        print("Conversion process completed successfully!")
        print("--------------------")

    except Exception as e:
        print("\n--------------------")
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        print("--------------------")

    finally:
        print("Closing Neo4j connection.")
        converter.close()