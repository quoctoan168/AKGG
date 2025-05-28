import os
from owlready2 import get_ontology
from neo4j import GraphDatabase
from ask_monica import ask_monica
from prompt_builder import Prompt

class KnowledgeGraphBuilder:
    def __init__(self, owl_file, neo4j_uri, neo4j_user, neo4j_password, model="gpt-4o", key_file="API_Key.txt"):
        self.owl_file = owl_file
        self.model = model
        self.key_file = key_file
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.onto = None
        self.classes = []
        self.datatype_props = []
        self.object_props = []

    def load_ontology(self):
        if not os.path.exists(self.owl_file):
            raise FileNotFoundError(f"OWL file not found: {self.owl_file}")
        self.onto = get_ontology(f"file://{self.owl_file}").load()
        self.classes = [cls.name for cls in self.onto.classes()]
        self.datatype_props = [prop.name for prop in self.onto.data_properties()]
        self.object_props = [prop.name for prop in self.onto.object_properties()]

    def build_prompt(self, text):
        # Đảm bảo ontology đã được tải trước khi xây dựng prompt
        if self.onto is None:
            self.load_ontology()

        # Các thành phần của prompt
        task_desc = "Trích xuất các thực thể và quan hệ từ văn bản dựa trên ontology đã cho."
        context = (
            f"Ontology đã tải từ '{self.owl_file}'."
            f" Các lớp (Classes): {', '.join(self.classes)}."
            f" Quan hệ đối tượng (Object Properties): {', '.join(self.object_props)}."
            f" Thuộc tính dữ liệu (Datatype Properties): {', '.join(self.datatype_props)}."
        )
        goal = "Xác định các thực thể (instance) và các quan hệ (object property) như định nghĩa trong ontology."
        output_fmt = (
            "[Entities]\n- EntityName (ClassName)"
            "\n[Relationships]\n- EntityName1 -[RelationshipName]-> EntityName2"
        )
        constraints = (
            "Chỉ trích xuất các thực thể và quan hệ đã có trong ontology. "
            "Không được tạo mới hoặc sử dụng bất kỳ class, property, hoặc relation nào ngoài danh sách này. "
            "Bỏ qua các phần không khớp và không thêm giải thích hoặc kết luận nào."
        )

        # Xây dựng prompt bằng Prompt class
        prompt = Prompt(
            task_description=task_desc,
            context=context,
            input_data=text,
            goal=goal,
            output_format=output_fmt,
            constraints=constraints
        )
        return prompt.build()

    def extract_kg(self, text):
        prompt_text = self.build_prompt(text)
        ai_response = ask_monica(prompt_text, model=self.model, key_file=self.key_file)
        if not ai_response:
            print("❌ LLM không trả về kết quả.")
            return [], []

        entities, relationships = [], []
        section = None
        for line in ai_response.splitlines():
            line = line.strip()
            if line == "[Entities]":
                section = "entities"
            elif line == "[Relationships]":
                section = "relationships"
            elif line and section:
                if section == "entities" and line.startswith("-"):
                    entities.append(line[1:].strip())
                elif section == "relationships" and line.startswith("-"):
                    relationships.append(line[1:].strip())
        return entities, relationships

    def store_in_neo4j(self, entities, relationships):
        with self.driver.session() as session:
            # Tạo nodes
            entity_map = {}
            for entity in entities:
                try:
                    name, class_name = entity.split(" (")
                    class_name = class_name.rstrip(")")
                    if class_name in self.classes:
                        session.run(
                            "MERGE (n:Instance {name: $name, class: $class_})",
                            name=name, class_=class_name
                        )
                        entity_map[name] = class_name
                except ValueError:
                    continue

            # Tạo relationships
            for rel in relationships:
                try:
                    parts = rel.split(" -[")
                    source = parts[0].strip()
                    rel_target = parts[1].split("]-> ")
                    rel_name = rel_target[0]
                    target = rel_target[1].strip()
                    if (rel_name in self.object_props and 
                        source in entity_map and 
                        target in entity_map):
                        session.run(
                            """
                            MATCH (a:Instance {name: $source})
                            MATCH (b:Instance {name: $target})
                            MERGE (a)-[r:RELATION {type: $rel_name}]->(b)
                            """,
                            source=source, target=target, rel_name=rel_name
                        )
                except Exception:
                    continue

    def build_from_text(self, text, clear_db=False):
        self.load_ontology()
        entities, relationships = self.extract_kg(text)
        if clear_db:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                print("✅ Đã xóa sạch dữ liệu Neo4j")
        self.store_in_neo4j(entities, relationships)

    def close(self):
        self.driver.close()


# ==============================
# MAIN PIPELINE (batch input)
# ==============================

if __name__ == "__main__":
    ontology_file = "output/seed_ontology.owl"
    input_folder = "input_text"
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"
    model = "gpt-4o"
    key_file = "API_Key.txt"
    clear_db_first = True

    input_files = sorted([
        os.path.join(input_folder, fn) for fn in os.listdir(input_folder)
        if fn.lower().endswith(".txt")
    ])

    if not input_files:
        print(f"❌ Không có file txt trong thư mục {input_folder}")
        exit(1)

    for idx, file_path in enumerate(input_files):
        print(f"\n🟦 [{idx+1}/{len(input_files)}] Xử lý: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        kg = KnowledgeGraphBuilder(
            ontology_file, neo4j_uri, neo4j_user, neo4j_password, model, key_file
        )
        try:
            kg.build_from_text(text, clear_db=(clear_db_first and idx == 0))
            print("✅ Done!")
        except Exception as e:
            print(f"❌ Lỗi với {file_path}: {e}")
        finally:
            kg.close()
