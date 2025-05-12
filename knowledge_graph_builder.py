from owlready2 import get_ontology
from neo4j import GraphDatabase
from prompt_builder import Prompt
from ontology_builder import OntologyBuilder
import os

class knowledge_graph_builder:
    def __init__(self, owl_file, text_file, neo4j_uri="bolt://localhost:7687", neo4j_user="neo4j", neo4j_password="12345678", model="gpt-4o", key_file="API_Key.txt"):
        """Initialize with OWL file, text file, Neo4j connection, and AI model details."""
        self.owl_file = owl_file
        self.text_file = text_file
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.onto = None
        self.builder = OntologyBuilder(model=model, key_file=key_file)  # Reuse OntologyBuilder for AI calls
        self.classes = []
        self.datatype_props = []
        self.object_props = []

    def load_ontology(self):
        """Load the OWL ontology and extract classes, datatype properties, and object properties."""
        if not os.path.exists(self.owl_file):
            raise FileNotFoundError(f"OWL file not found: {self.owl_file}")
        self.onto = get_ontology(f"file://{self.owl_file}").load()
        self.classes = [cls.name for cls in self.onto.classes()]
        self.datatype_props = [prop.name for prop in self.onto.data_properties()]
        self.object_props = [prop.name for prop in self.onto.object_properties()]
        print(f"✅ Loaded ontology: Classes={self.classes}, Datatype Props={self.datatype_props}, Object Props={self.object_props}")

    def load_text(self):
        """Load the input text from file."""
        if not os.path.exists(self.text_file):
            raise FileNotFoundError(f"Text file not found: {self.text_file}")
        with open(self.text_file, "r", encoding="utf-8") as f:
            return f.read().strip()

    def create_prompt(self, text):
        """Create a prompt to extract entities and relationships from text based on ontology."""
        ontology_summary = (
            f"Classes: {', '.join(self.classes)}\n"
            f"Object Properties: {', '.join(self.object_props)}"
        )
        prompt = Prompt(
            task_description="Extract entities and relationships from the provided text based on the given ontology.",
            context="The ontology defines the structure for a Knowledge Graph about Vietnamese history. Use it to identify relevant entities and their relationships in the text.",
            input_data=text,
            goal="Identify entities (instances of ontology classes) and relationships (object properties) as defined in the ontology.",
            output_format=(
                "Return the result in the following format:\n"
                "[Entities]\n"
                "- EntityName (ClassName)\n"
                "...\n"
                "[Relationships]\n"
                "- EntityName1 -[RelationshipName]-> EntityName2\n"
                "..."
            ),
            constraints=(
                f"Only extract entities and relationships that match the ontology:\n{ontology_summary}\n"
                "Do not invent new classes or relationships.\n"
                "Ensure entity names are unique and meaningful based on the text context.\n"
                "Every entity mentioned in relationships MUST be included in the [Entities] section with a class from the ontology.\n"
                "Use only object properties defined in the ontology for relationships.\n"
                "If an entity’s class is ambiguous, select the most relevant class from the ontology based on the context or the range of the object property it’s associated with."
            )
        )
        return prompt.build()

    def extract_kg_elements(self, text):
        """Call the AI to extract entities and relationships from text."""
        prompt_text = self.create_prompt(text)
        response = self.builder._call_ai(prompt_text)
        print("✅ AI Response:\n", response)
        return self.parse_ai_response(response)

    def parse_ai_response(self, response):
        """Parse the AI response into entities and relationships."""
        entities = []
        relationships = []
        current_section = None

        for line in response.splitlines():
            line = line.strip()
            if line == "[Entities]":
                current_section = "entities"
            elif line == "[Relationships]":
                current_section = "relationships"
            elif line and current_section:
                if current_section == "entities" and line.startswith("-"):
                    entities.append(line[1:].strip())
                elif current_section == "relationships" and line.startswith("-"):
                    relationships.append(line[1:].strip())

        return entities, relationships

    def store_in_neo4j(self, entities, relationships):
        """Store the extracted elements in Neo4j, ensuring all entities exist before creating relationships."""
        with self.driver.session() as session:
            # Collect all unique entities and their classes
            all_entities = set()
            entity_class_map = {}

            # From entities section
            for entity in entities:
                try:
                    name, class_name = entity.split(" (")
                    class_name = class_name.rstrip(")")
                    if class_name in self.classes:
                        all_entities.add(name)
                        entity_class_map[name] = class_name
                    else:
                        print(f"⚠️ Invalid class for entity: {entity} (class {class_name} not in ontology)")
                except ValueError:
                    print(f"⚠️ Invalid entity format: {entity}")

            # From relationships
            for rel in relationships:
                try:
                    parts = rel.split(" -[")
                    source = parts[0].strip()
                    rel_target = parts[1].split("]-> ")
                    target = rel_target[1].strip()
                    all_entities.add(source)
                    all_entities.add(target)
                except (IndexError, ValueError):
                    print(f"⚠️ Invalid relationship format: {rel}")

            # Create nodes for all entities
            for entity_name in all_entities:
                # Assign class based on ontology, default to first class if not specified
                class_name = entity_class_map.get(entity_name)
                if not class_name:
                    # Infer class based on relationships
                    for rel in relationships:
                        try:
                            parts = rel.split(" -[")
                            source = parts[0].strip()
                            rel_target = parts[1].split("]-> ")
                            rel_name = rel_target[0]
                            target = rel_target[1].strip()
                            if rel_name in self.object_props and target == entity_name:
                                prop = self.onto[rel_name]
                                range_classes = [r.name for r in prop.range] if prop.range else []
                                if range_classes:
                                    class_name = range_classes[0]
                                    break
                        except (IndexError, ValueError):
                            continue
                    # Fallback to first ontology class if no class inferred
                    class_name = class_name or self.classes[0] if self.classes else "Unknown"

                if class_name in self.classes:
                    session.run(
                        "MERGE (i:Instance {name: $name, class: $class_})",
                        name=entity_name, class_=class_name
                    )
                    print(f"Created node: {entity_name} (class: {class_name})")
                    entity_class_map[entity_name] = class_name
                else:
                    print(f"⚠️ Skipping node creation for {entity_name} (invalid class: {class_name})")

            # Create relationships only between valid entities
            for rel in relationships:
                try:
                    parts = rel.split(" -[")
                    source = parts[0].strip()
                    rel_target = parts[1].split("]-> ")
                    rel_name = rel_target[0]
                    target = rel_target[1].strip()
                    if (source in all_entities and target in all_entities and
                            entity_class_map[source] in self.classes and
                            entity_class_map[target] in self.classes and
                            rel_name in self.object_props):
                        # Validate relationship against ontology range
                        prop = self.onto[rel_name]
                        range_classes = [r.name for r in prop.range] if prop.range else []
                        if entity_class_map[target] in range_classes:
                            session.run(
                                """
                                MATCH (a:Instance {name: $source})
                                MATCH (b:Instance {name: $target})
                                MERGE (a)-[r:RELATION {type: $rel_name}]->(b)
                                """,
                                source=source, target=target, rel_name=rel_name
                            )
                            print(f"Created relationship: {source} -[{rel_name}]-> {target}")
                        else:
                            print(f"⚠️ Skipping relationship: {source} -[{rel_name}]-> {target} (target class {entity_class_map[target]} not in range {range_classes})")
                    else:
                        print(f"⚠️ Skipping relationship due to invalid entity or property: {source}, {target}, or {rel_name}")
                except (IndexError, ValueError):
                    print(f"⚠️ Invalid relationship format: {rel}")

    def build_kg(self, clear_db=False):
        """Build the Knowledge Graph from text using the ontology."""
        print("▶️ Building Knowledge Graph from text...")
        self.load_ontology()
        text = self.load_text()
        entities, relationships = self.extract_kg_elements(text)
        if clear_db:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                print("✅ Cleared Neo4j database")
        self.store_in_neo4j(entities, relationships)
        print("✅ Knowledge Graph built successfully")

    def close(self):
        """Close the Neo4j driver connection."""
        self.driver.close()
        print("✅ Closed Neo4j connection")

def main():
    # Example usage
    owl_file = "seed_ontology.owl"  # Adjust path as needed
    text_file = "input_text.txt"  # Adjust path as needed
    kg_builder = knowledge_graph_builder(
        owl_file=owl_file,
        text_file=text_file,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="12345678",  # Update with your Neo4j password
        model="gpt-4o",
        key_file="API_Key.txt"
    )
    try:
        # Write the input text to a file (for this example)
        input_text = """Nước Việt Nam
1. Quốc Hiệu
2. Vị Trí và Diện Tích
3. Địa Thế
4. Chủng Loại
5. Gốc Tích
6. Người Việt Nam
7. Sự Mở Mang Bờ Cõi
8. Lịch Sử Việt Nam
1. Quốc Hiệu. Nước Việt Nam ta về đời Hồng Bàng (2897 - 258 trước
Tây lịch) gọi là Văn Lang, đời Thục An Dương Vương (257 - 207 trước Tây
lịch) thì gọi là Âu Lạc. Đến nhà Tần (246 - 206 trước Tây lịch) lược định phía
nam thì đặt làm Tượng Quận, sau nhà Hán (202 trước Tây lịch - 220 sau Tây
lịch) dứt nhà Triệu, chia đất Tượng Quận ra làm ba quận là Giao Chỉ, Cửu
Chân và Nhật Nam. Đến cuối đời nhà Đông Hán, vua Hiến Đế đổi Giao Chỉ
làm Giao Châu. Nhà Đường lại đặt là An Nam Đô Hộ Phủ.
Từ khi nhà Đinh (968 - 980) dẹp xong loạn Thập Nhị Sứ Quân, lập nên một
nước tự chủ, đổi quốc hiệu là Đại Cồ Việt. Vua Lý Thánh Tông đổi là Đại
Việt, đến đời vua Anh Tông, nhà Tống bên Tàu mới công nhận là An Nam
Quốc.
Đến đời vua Gia Long, thống nhất được cả Nam Bắc (1802), lấy lẽ
rằng Nam là An Nam, Việt là Việt Thường, mới đặt quốc hiệu là Việt Nam.
Vua Minh Mệnh lại cải làm Đại Nam.
 Quốc hiệu nước ta thay đổi đã nhiều lần, tuy rằng ngày nay ta vẫn
theo thói quen dùng hai chữ An Nam, nhưng vì hai chữ ấy có ngụ ý phải
thần phục nước Tàu, vậy thì ta nên nhất định lấy tên Việt Nam mà gọi nước
nhà.
2. Vị Trí và Diện Tích. Nước Việt Nam ở về phía đông nam châu Átế-á, hẹp bề ngang, dài bề dọc, hình cong như chữ S, trên phía bắc và dưới
phía nam phình rộng ra, khúc giữa miền trung thì eo hẹp lại. 
Đông và nam giáp bể Trung Quốc (tức là bể Nam Hải); Tây giáp Ai
Lao và Cao Miên; Bắc giáp nước Tàu, liền với tỉnh QuảngĐông, Quảng Tâyvà Vân Nam.
Diện tích cả nước rộng chừng độ 312.000 ki-lô-mét vuông chia ra như sau này:
 Bắc Việt: 105.000 km2
 Trung Việt: 150.000 km2
 Nam Việt: 57.000 km2 """
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(input_text)
        
        kg_builder.build_kg(clear_db=True)
    finally:
        kg_builder.close()

if __name__ == "__main__":
    main()