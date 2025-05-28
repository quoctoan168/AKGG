from ontology_builder import OntologyBuilder

builder = OntologyBuilder(model="gpt-4o")
builder.set_description("Tôi đang xây dựng một hệ thống để lưu trữ thông tin về lịch sử Việt Nam và tra cứu các sự kiện lịch sử.")
builder.set_purpose("Lưu trữ và tra cứu thông tin lịch sử.")
# Đọc input từ file
with open("input_text/01.txt", "r", encoding="utf-8") as f:
    input_text = f.read()
builder.set_input_text(input_text)

builder.run_Seeding()  # In ra 12 CQ Answers và Seed‑Ontology
