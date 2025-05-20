from prompt_builder import Prompt
from owlready2      import get_ontology, Thing, ObjectProperty, DataProperty, sync_reasoner_pellet
import requests, json, re, types, os
from ask_monica import ask_monica
import unicodedata

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
        return ask_monica(
        prompt_text,
        model=getattr(self, "model", "gpt-4o"),
        key_file=getattr(self, "key_file", "API_Key.txt")
    )

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
        # --- Tách câu trả lời theo từng CQ bằng regex ---
        pattern = r"(CQ\d{1,2}:\s)"
        parts = re.split(pattern, self.cq_answers)
        cq_dict = {}
        for i in range(1, len(parts), 2):
            key = parts[i].strip()  # CQ1:
            val = parts[i + 1].strip() if i + 1 < len(parts) else ""
            cq_dict[key] = val

        # --- Lưu ra file với định dạng: CÂU HỎI + CÂU TRẢ LỜI ---
        os.makedirs("ontology_output", exist_ok=True)
        with open("ontology_output/cq_answers.txt", "w", encoding="utf-8") as f:
            for i in range(1, 13):
                key = f"CQ{i}"
                question = cq_questions[i - 1] if i - 1 < len(cq_questions) else "Câu hỏi không rõ"
                answer = cq_dict.get(f"{key}:", "[Không có câu trả lời]")
                f.write(f"{question}\n{answer}\n\n")

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
            "Dựa trên 12 CQ sau, LIỆT KÊ lớp, mỗi dòng ở dạng '- id: ... | label: ...' (id là tên PascalCase tiếng Việt không dấu, label là tên đầy đủ có dấu):\n"
        "\nVí dụ:\n- id: QuocHieu | label: Quốc Hiệu\n- id: NguoiVietNam | label: Người Việt Nam\n"+
        self.cq_answers +
        "\nCHỈ trả về danh sách, KHÔNG được thêm giải thích, ví dụ, lời dẫn, kết luận. Không thêm bất kỳ dòng nào ngoài kết quả theo format yêu cầu!"
        "\nOutput must be strictly only the requested list, nothing else."
        )
        self.class_text = self._call_ai(prompt)
        return self.class_text

    # ---------- phase 2: DatatypeProperty ----------
    def generate_properties(self):
        if self.prop_text is not None:
            return self.prop_text
        prompt = (
        "Cho danh sách lớp dưới đây (theo dạng '- id: ... | label: ...'), tạo THUỘC TÍNH DỮ LIỆU cho từng lớp, mỗi thuộc tính ở dạng 'class_id: prop_id|label, ...'. "
        "prop_id là tên thuộc tính không dấu, label là tiếng Việt đầy đủ. Ví dụ: NguoiVietNam: ten|Tên, tuoi|Tuổi\n"
        + self.class_text+
        "\nCHỈ trả về danh sách, KHÔNG được thêm giải thích, ví dụ, lời dẫn, kết luận. Không thêm bất kỳ dòng nào ngoài kết quả theo format yêu cầu!"
        "\nOutput must be strictly only the requested list, nothing else."
        )
        self.prop_text = self._call_ai(prompt)
        return self.prop_text

    # ---------- phase 3: ObjectProperty ----------
    def generate_relations(self):
        if self.rel_text is not None:
            return self.rel_text
        prompt = (
        "Cho CLASSES + PROPERTIES sau, tạo QUAN HỆ giữa các lớp, mỗi dòng ở dạng '- id: quanHeId | label: Tên quan hệ | (ClassA_id → ClassB_id)':\n"
        + self.class_text + "\n\n" + self.prop_text +
        "\nVí dụ:\n- id: thuocQuocHieu | label: Thuộc Quốc Hiệu | (NguoiVietNam → QuocHieu)\n"
        "\nKHÔNG được thêm lời giải thích, ví dụ, mở đầu, kết luận, chỉ trả về danh sách quan hệ đúng format yêu cầu."
        "\nOutput must be strictly only the requested list, nothing else."
        )
        self.rel_text = self._call_ai(prompt)
        return self.rel_text

    # ---------- build OWL ----------
    def parse_id_label(line):
        # line: "- id: QuocHieu | label: Quốc Hiệu"
        match = re.match(r"-?\s*id:\s*([^\|]+)\|\s*label:\s*(.+)", line)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None, None

    
    def build_owl_and_check(self, owl_file="seed_ontology.owl", ns="http://example.org/seed.owl#", run_reasoner=True):
        # Parse classes
        class_map = {}
        for l in self.class_text.splitlines():
            if "id:" in l and "label:" in l:
                cid, clabel = OntologyBuilder.parse_id_label(l)
                if cid:
                    class_map[cid] = {"label": clabel}

        # Parse properties
        prop_map = {}  # {class_id: [(prop_id, prop_label), ...]}
        for l in self.prop_text.splitlines():
            if ":" in l:
                class_id, props = l.split(":", 1)
                props = props.strip()
                pairs = [p.strip() for p in props.split(",") if "|" in p]
                prop_map[class_id.strip()] = [(p.split("|")[0].strip(), p.split("|")[1].strip()) for p in pairs]

        # Parse relations
        rels = []  # list of (rel_id, rel_label, dom_id, rng_id)
        for l in self.rel_text.splitlines():
            m = re.match(r"-?\s*id:\s*([^\|]+)\|\s*label:\s*([^\|]+)\|\s*\((.+?)\s*→\s*(.+?)\)", l)
            if m:
                rel_id, rel_label, dom, rng = m.groups()
                rels.append((rel_id.strip(), rel_label.strip(), dom.strip(), rng.strip()))

        onto = get_ontology(ns)
        with onto:
            # Tạo class
            cmap = {}
            for cid, info in class_map.items():
                owl_cls = types.new_class(cid, (Thing,))
                owl_cls.label = info["label"]
                cmap[cid] = owl_cls
            # Tạo property
            for class_id, plist in prop_map.items():
                if class_id in cmap:
                    for pid, plabel in plist:
                        dp = types.new_class(pid, (DataProperty,))
                        dp.domain = [cmap[class_id]]
                        dp.range = [str]
                        dp.label = plabel
            # Tạo object property
            for rel_id, rel_label, dom_id, rng_id in rels:
                if dom_id in cmap and rng_id in cmap:
                    op = types.new_class(rel_id, (ObjectProperty,))
                    op.domain = [cmap[dom_id]]
                    op.range = [cmap[rng_id]]
                    op.label = rel_label

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