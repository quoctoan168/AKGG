from ontology_builder import OntologyBuilder
from knowledge_graph_builder import KnowledgeGraphBuilder
import os

# Configuration
ontology_file = "seed_ontology.owl"
input_folder = "input_text"
neo4j_uri = "bolt://localhost:7687"
neo4j_user = "neo4j"
neo4j_password = "12345678"
model = "gpt-4o"
key_file = "API_Key.txt"
clear_db_first = True

# Initialize OntologyBuilder
builder = OntologyBuilder(model=model, key_file=key_file)
builder.set_description("Tôi đang xây dựng một hệ thống để lưu trữ thông tin về lịch sử Việt Nam và tra cứu các sự kiện lịch sử.")
builder.set_purpose("Lưu trữ và tra cứu thông tin lịch sử.")

# Get list of input text files
input_files = sorted([
    os.path.join(input_folder, fn) for fn in os.listdir(input_folder)
    if fn.lower().endswith(".txt")
])

if not input_files:
    print(f"❌ Không có file txt trong thư mục {input_folder}")
    exit(1)

# Process each input file
for idx, file_path in enumerate(input_files):
    print(f"\n🟦 [{idx+1}/{len(input_files)}] Xử lý: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        input_text = f.read()
    
    # Set input text for OntologyBuilder
    builder.set_input_text(input_text)
    
    # Step 1: Generate CQ answers and seed ontology if it's the first file
    if idx == 0:
        print("▶️ Generating CQ answers and seed ontology...")
        builder.run_Seeding()
    else:
        # Step 2: Update ontology with new text
        print("▶️ Updating ontology with new text...")
        builder.update_ontology_from_text(input_text, owl_file=ontology_file)
    
    # Step 3: Build knowledge graph
    print("▶️ Building knowledge graph...")
    kg = KnowledgeGraphBuilder(
         "output/seed_ontology.owl", neo4j_uri, neo4j_user, neo4j_password, model, key_file
    )
    try:
        kg.build_from_text(input_text, clear_db=(clear_db_first and idx == 0))
        print("✅ Done!")
    except Exception as e:
        print(f"❌ Lỗi với {file_path}: {e}")
    finally:
        kg.close()