from datetime import date, datetime
from neo4j import GraphDatabase
from objects import objects_list


class Neo4jConverter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._saved_nodes = {}  # id(obj) -> Neo4j elementId
        self._processing = set()  # Set to track objects being processed (prevent infinite recursion)

    def close(self):
        self.driver.close()

    def _serialize_value(self, value):
        """Convert Python values to Neo4j-compatible format"""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        elif isinstance(value, (date, datetime)):
            return value.isoformat()
        elif isinstance(value, complex):
            return str(value)
        elif isinstance(value, (list, tuple, set)):
            return [self._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return str(value)

    def _create_node(self, obj, label=None):
        """Create a node for an object or collection"""
        obj_id = id(obj)
        if obj_id in self._saved_nodes:
            return self._saved_nodes[obj_id]  # Return existing node ID

        # Determine label and properties based on object type
        if isinstance(obj, (list, tuple, set)):
            label = "Collection"
            properties = {"type": type(obj).__name__, "length": len(obj)}
        elif isinstance(obj, dict):
            label = "Dictionary"
            properties = {"length": len(obj)}
        elif not hasattr(obj, "__dict__"):
            # For primitive values
            label = "Value"
            properties = {"value": self._serialize_value(obj), "type": type(obj).__name__}
        else:
            # For class instances
            label = label or obj.__class__.__name__
            properties = {}
            for attr, value in vars(obj).items():
                if self._is_basic_type(value) or isinstance(value, (list, tuple, set, dict)):
                    if self._is_basic_type(value):
                        properties[attr] = self._serialize_value(value)

        # Create the node
        prop_keys = ", ".join(f"{k}: ${k}" for k in properties)
        query = f"CREATE (n:{label} {{{prop_keys}}}) RETURN elementId(n)"

        with self.driver.session() as session:
            result = session.run(query, **properties)
            element_id = result.single()[0]
            self._saved_nodes[obj_id] = element_id
            return element_id

    def _create_relationship(self, from_id, to_id, rel_type):
        """Create a relationship between two nodes by element IDs"""
        # Clean up relationship type for Neo4j
        rel_type = rel_type.replace(" ", "_").replace("-", "_").upper()

        query = f"""
        MATCH (a) WHERE elementId(a) = $from_id
        MATCH (b) WHERE elementId(b) = $to_id
        MERGE (a)-[r:{rel_type}]->(b)
        """
        with self.driver.session() as session:
            session.run(query, from_id=from_id, to_id=to_id)

    def _is_basic_type(self, val):
        """Check if a value is a primitive type that can be stored directly as a property"""
        return isinstance(val, (str, int, float, bool, type(None), datetime, date))

    def save(self, obj):
        """Save an object and all its relationships to Neo4j"""
        self._saved_nodes = {}  # Reset saved nodes
        self._processing = set()  # Reset processing tracker
        self._recursive_save(obj)

    def _handle_collection(self, collection, parent_id):
        """Process a collection (list, tuple, set) and link items to parent"""
        # Create a node for the collection if not already created
        collection_id = id(collection)
        if collection_id not in self._saved_nodes:
            self._create_node(collection)
        collection_node_id = self._saved_nodes[collection_id]

        # Link parent to collection if parent exists
        if parent_id is not None:
            self._create_relationship(parent_id, collection_node_id, "HAS_COLLECTION")

        # Add items to collection
        for i, item in enumerate(collection):
            # Create node for the item
            if self._is_basic_type(item):
                # For basic types, create a Value node
                item_node_id = self._create_node(item)
                self._saved_nodes[id(item)] = item_node_id
                # Link collection to item with index
                self._create_relationship(collection_node_id, item_node_id, f"ITEM_AT_{i}")
            elif isinstance(item, (list, tuple, set)):
                # Handle nested collection
                self._handle_collection(item, collection_node_id)
            elif isinstance(item, dict):
                # Handle dictionary
                self._handle_dictionary(item, collection_node_id)
            else:
                # Handle object
                if id(item) not in self._processing:
                    self._recursive_save(item, collection_node_id, f"ITEM_AT_{i}")

    def _handle_dictionary(self, dictionary, parent_id=None):
        """Process a dictionary and link entries to parent"""
        # Create a node for the dictionary
        dict_id = id(dictionary)
        if dict_id not in self._saved_nodes:
            self._create_node(dictionary)
        dict_node_id = self._saved_nodes[dict_id]

        # Link parent to dictionary if parent exists
        if parent_id is not None:
            self._create_relationship(parent_id, dict_node_id, "HAS_DICTIONARY")

        # Add entries to dictionary
        for key, value in dictionary.items():
            key_str = str(key).replace(" ", "_").upper()

            if self._is_basic_type(value):
                # For basic types, create a Value node
                value_node_id = self._create_node(value)
                self._saved_nodes[id(value)] = value_node_id
                # Link dictionary to value with key
                self._create_relationship(dict_node_id, value_node_id, f"KEY_{key_str}")
            elif isinstance(value, (list, tuple, set)):
                # Handle collection
                self._handle_collection(value, dict_node_id)
            elif isinstance(value, dict):
                # Handle nested dictionary
                self._handle_dictionary(value, dict_node_id)
            else:
                # Handle object
                if id(value) not in self._processing:
                    self._recursive_save(value, dict_node_id, f"KEY_{key_str}")

    def _recursive_save(self, obj, parent_id=None, rel_type="HAS"):
        """Recursively save an object and its relationships"""
        # Skip None values
        if obj is None:
            return

        # Check if we're already processing this object to prevent cycles
        obj_id = id(obj)
        if obj_id in self._processing:
            # Just create the relationship if needed, but don't recurse
            if parent_id is not None and obj_id in self._saved_nodes:
                self._create_relationship(parent_id, self._saved_nodes[obj_id], rel_type)
            return

        # Mark this object as being processed
        self._processing.add(obj_id)

        try:
            # Create node for this object if needed
            if obj_id not in self._saved_nodes:
                self._create_node(obj)
            node_id = self._saved_nodes[obj_id]

            # Create relationship from parent if needed
            if parent_id is not None:
                self._create_relationship(parent_id, node_id, rel_type)

            # Handle different types of objects
            if isinstance(obj, (list, tuple, set)):
                # Handle collections directly
                self._handle_collection(obj, parent_id)
            elif isinstance(obj, dict):
                # Handle dictionaries directly
                self._handle_dictionary(obj, parent_id)
            elif hasattr(obj, "__dict__"):
                # Process class instance attributes
                for attr, value in vars(obj).items():
                    # Skip basic types as they're already saved as properties
                    if self._is_basic_type(value):
                        continue

                    # Handle collections and nested objects
                    if isinstance(value, (list, tuple, set)):
                        self._handle_collection(value, node_id)
                    elif isinstance(value, dict):
                        self._handle_dictionary(value, node_id)
                    else:
                        # Regular object reference
                        self._recursive_save(value, node_id, attr.upper())
        finally:
            # Remove from processing set when done
            self._processing.remove(obj_id)


if __name__ == "__main__":
    converter = Neo4jConverter(uri="bolt://localhost:7687", user="neo4j", password="password")
    try:
        for obj in objects_list:
            print(f"Saving {obj.__class__.__name__}...")
            converter.save(obj)
        print("SUCCESSFUL")
    finally:
        converter.close()