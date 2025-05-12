from prompt_builder import Prompt
from owlready2      import get_ontology, Thing, ObjectProperty, DataProperty, sync_reasoner_pellet
import requests, json, re, types, os

# =============== CẤU HÌNH API ===============
def _read_api_key(file_path="API_Key.txt", model_name="monica"):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(f"{model_name}:"):
                    return line.split(":", 1)[1].strip()
    except FileNotFoundError:
        print("❌ Không tìm thấy file API_Key.txt")
    return None

class OntologyBuilder:
    ENDPOINT = "https://openapi.monica.im/v1/chat/completions"

    def __init__(self, model="gpt-4o", key_file="API_Key.txt"):
        self.model       = model
        self.api_key     = _read_api_key(key_file)
        if not self.api_key:
            raise RuntimeError("API key không hợp lệ.")

        self.user_desc   = None
        self.kg_purpose  = None
        self.raw_text    = None
        self.cq_answers  = None
        self.seed_onto   = None
        self.owl_path    = None
        self.class_text  = None
        self.prop_text   = None
        self.rel_text    = None

    # ---------- thiết lập ----------
    def set_description(self, desc): self.user_desc = desc.strip()
    def set_purpose    (self, p   ): self.kg_purpose = p.strip()
    def set_input_text (self, txt ): self.raw_text   = txt.strip()

    # ---------- gọi API ----------
    def _call_ai(self, prompt_text):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json"
        }
        messages = [
            {"role": "system", "content": "Bạn là API, trả đúng format, không thêm gì khác."},
            {"role": "user",
             "content": [{"type": "text", "text": prompt_text}]}
        ]
        data = {"model": self.model, "messages": messages, "temperature": 0, "stream": False}
        res  = requests.post(self.ENDPOINT, headers=headers, json=data)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()

    # ---------- bước 1: 12 CQ ----------
    def generate_cq_answers(self):
        cq_questions = [
            "CQ1: Miền tri thức (domain) là gì?",
            "CQ2: Mục tiêu chính của Knowledge Graph là gì?",
            "CQ3: Những thực thể (class) cốt lõi cần mô hình hóa là gì?",
            "CQ4: Thuộc tính (property) quan trọng của từng thực thể là gì?",
            "CQ5: Quan hệ (relation) chủ chốt giữa các thực thể là gì?",
            "CQ6: Ví dụ cụ thể (instance) cho mỗi lớp là gì?",
            "CQ7: Có ràng buộc nghiệp vụ (constraint) nào không?",
            "CQ8: Có yêu cầu đặc tính lớp (bắt buộc, duy nhất, temporal) không?",
            "CQ9: Có yếu tố thời gian nào cần mô hình hóa không?",
            "CQ10: Có cần lưu thông tin nguồn gốc (provenance) dữ liệu không?",
            "CQ11: Yêu cầu về chất lượng/độ tin cậy dữ liệu ra sao?",
            "CQ12: Ai là người dùng cuối và họ sẽ truy vấn như thế nào?"
        ]
        prompt_text = Prompt(
            task_description="Trả lời 12 Competency Questions (CQ).",
            context=self.user_desc,
            input_data=self.raw_text,
            goal=f"Trả lời 12 CQ (mục đích KG: {self.kg_purpose}).",
            output_format=("Đúng định dạng:\nCQ1: ...\n...\nCQ12: ..."),
            constraints="Không thêm lời dẫn, ký tự lạ.",
        ).build() + "\n\n[CÁC CÂU HỎI]\n" + "\n".join(cq_questions)

        self.cq_answers = self._call_ai(prompt_text)
        return self.cq_answers

    # ---------- bước 2: seed ontology ----------
    def generate_seed_ontology(self):
        if not self.cq_answers:
            raise RuntimeError("Chưa có câu trả lời 12 CQ.")

        # Gọi các hàm để tạo classes, properties, và relations
        self.class_text = self.generate_classes()
        self.prop_text = self.generate_properties()
        self.rel_text = self.generate_relations()

        # Tổng hợp seed ontology
        seed_onto_lines = []
        seed_onto_lines.append("=== Seed Ontology ===")
        seed_onto_lines.append("\n# Classes")
        seed_onto_lines.append(self.class_text or "No classes generated.")
        seed_onto_lines.append("\n# Datatype Properties")
        seed_onto_lines.append(self.prop_text or "No properties generated.")
        seed_onto_lines.append("\n# Object Properties")
        seed_onto_lines.append(self.rel_text or "No relations generated.")

        # Lưu và trả về seed ontology
        self.seed_onto = "\n".join(seed_onto_lines)
        return self.seed_onto

    # ---------- phase 1: Class ----------
    def generate_classes(self):
        if self.class_text is not None:
            return self.class_text
        prompt = (
            "Dựa trên 12 CQ sau, LIỆT KÊ lớp, mỗi dòng '- Tên_Lớp':\n" +
            self.cq_answers
        )
        self.class_text = self._call_ai(prompt)
        return self.class_text

    # ---------- phase 2: DatatypeProperty ----------
    def generate_properties(self):
        if self.prop_text is not None:
            return self.prop_text
        prompt = (
            "Cho danh sách lớp dưới đây, tạo THUỘC TÍNH DỮ LIỆU cho từng lớp theo mẫu 'Class: prop1, prop2':\n" +
            "Ví dụ: Nếu lớp là 'Person', trả về 'Person: name, age'\n" +
            "Đảm bảo mỗi lớp được liệt kê phải khớp chính xác với danh sách lớp đã cho.\n" +
            self.class_text
        )
        self.prop_text = self._call_ai(prompt)
        return self.prop_text

    # ---------- phase 3: ObjectProperty ----------
    def generate_relations(self):
        if self.rel_text is not None:
            return self.rel_text
        prompt = (
            "Cho CLASSES + PROPERTIES sau, tạo QUAN HỆ dạng '- tenQuanHe (ClassA → ClassB)':\n" +
            self.class_text + "\n\n" + self.prop_text
        )
        self.rel_text = self._call_ai(prompt)
        return self.rel_text

    # ---------- build OWL ----------
    def build_owl_and_check(self, owl_file="seed_ontology.owl", ns="http://example.org/seed.owl#", run_reasoner=True):
        # tách dữ liệu
        classes = [re.sub(r"^- ?", "", l).strip() for l in self.class_text.splitlines() if l.startswith("-")]
        props   = [l.strip() for l in self.prop_text.splitlines() if ":" in l]
        rels    = [re.sub(r"^- ?", "", l).strip() for l in self.rel_text.splitlines() if l.startswith("-")]

        onto = get_ontology(ns)
        with onto:
            # lớp
            cmap = {c.replace(" ", "_"): types.new_class(c.replace(" ", "_"), (Thing,)) for c in classes}
            # datatype property
            for line in props:
                if ":" not in line:
                    print(f"⚠️ Định dạng thuộc tính không hợp lệ, bỏ qua: {line}")
                    continue
                cls_name, plist = [x.strip() for x in line.split(":", 1)]
                cls_name_key = cls_name.replace(" ", "_")
                if cls_name_key not in cmap:
                    print(f"⚠️ Lớp '{cls_name}' không tồn tại trong danh sách lớp, bỏ qua thuộc tính: {line}")
                    continue
                for p in re.split(r",\s*", plist):
                    if not p.strip():
                        continue
                    dp = types.new_class(re.sub(r"\W", "_", p), (DataProperty,))
                    dp.domain = [cmap[cls_name_key]]
                    dp.range = [str]  # Giả sử kiểu dữ liệu mặc định là string
            # object property
            for r in rels:
                m = re.match(r"(.+?)\s*\((.+?)\s*→\s*(.+?)\)", r)
                if not m:
                    continue
                name, dom, rng = m.groups()
                op = types.new_class(re.sub(r"\W", "_", name), (ObjectProperty,))
                dkey, rkey = dom.replace(" ", "_"), rng.replace(" ", "_")
                if dkey in cmap:
                    op.domain = [cmap[dkey]]
                if rkey in cmap:
                    op.range = [cmap[rkey]]

        onto.save(file=owl_file, format="rdfxml")
        self.owl_path = owl_file
        if run_reasoner:
            with onto:
                sync_reasoner_pellet(infer_property_values=True)
        print("✅ Đã lưu OWL:", owl_file)
        return True

    # ---------- run full ----------
    def run(self):
        print("▶️ Trả lời 12 CQ …")
        print(self.generate_cq_answers())
        print("\n▶️ Sinh Seed‑Ontology …")
        print(self.generate_seed_ontology())
        print("\n▶️ Chuyển sang OWL & kiểm tra HermiT/Pellet …")
        self.build_owl_and_check()

    # ---------- lưu trạng thái ----------
    def save_state(self, folder_path="ontology_output"):
        os.makedirs(folder_path, exist_ok=True)
        with open(os.path.join(folder_path, "cq_answers.txt"), "w", encoding="utf-8") as f:
            f.write(self.cq_answers or "")
        with open(os.path.join(folder_path, "seed_ontology.txt"), "w", encoding="utf-8") as f:
            f.write(self.seed_onto or "")
        if self.owl_path:
            owl_dst = os.path.join(folder_path, os.path.basename(self.owl_path))
            os.replace(self.owl_path, owl_dst)
            self.owl_path = owl_dst
        print(f"✅ Đã lưu CQ, Seed-Ontology, OWL vào thư mục: {folder_path}")

    # ---------- tải lại trạng thái ----------
    def load_state(self, folder_path="ontology_output"):
        try:
            with open(os.path.join(folder_path, "cq_answers.txt"), "r", encoding="utf-8") as f:
                self.cq_answers = f.read()
            with open(os.path.join(folder_path, "seed_ontology.txt"), "r", encoding="utf-8") as f:
                self.seed_onto = f.read()
            owl_files = [f for f in os.listdir(folder_path) if f.endswith(".owl")]
            if owl_files:
                self.owl_path = os.path.join(folder_path, owl_files[0])
            print(f"✅ Đã tải lại dữ liệu từ: {folder_path}")
        except Exception as e:
            print("❌ Lỗi khi load state:", e)