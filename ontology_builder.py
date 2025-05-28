from prompt_builder import Prompt
from owlready2 import get_ontology, Thing, ObjectProperty, DataProperty, sync_reasoner_pellet
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
    ENDPOINT = "https://openapi.mMonica.im/v1/chat/completions"
    DEFAULT_OUTPUT_FOLDER = "output"
    CQ_QUESTIONS_FILE = "CQ_questions.txt"

    def __init__(self, model="gpt-4o", key_file="API_Key.txt"):
        self.model = model
        self.api_key = _read_api_key(key_file)
        if not self.api_key:
            raise RuntimeError("API key không hợp lệ.")

        self.user_desc = None
        self.kg_purpose = None
        self.raw_text = None
        self.cq_answers = None
        self.seed_onto = None
        self.owl_path = None
        self.class_text = None
        self.prop_text = None
        self.rel_text = None
        self.cq_questions = self._load_cq_questions()

    # ---------- tải CQ questions từ file ----------
    def _load_cq_questions(self, file_path=CQ_QUESTIONS_FILE):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                questions = [line.strip() for line in f if line.strip() and line.startswith("CQ")]
                if not questions:
                    raise ValueError("File CQ_questions.txt rỗng hoặc không chứa câu hỏi hợp lệ.")
                return questions
        except FileNotFoundError:
            print(f"❌ Không tìm thấy file {file_path}")
            return []
        except Exception as e:
            print(f"❌ Lỗi khi đọc file {file_path}: {e}")
            return []

    # ---------- thiết lập ----------
    def set_description(self, desc): self.user_desc = desc.strip()
    def set_purpose(self, p): self.kg_purpose = p.strip()
    def set_input_text(self, txt): self.raw_text = txt.strip()

    # ---------- gọi API ----------
    def _call_ai(self, prompt_text):
        return ask_monica(
            prompt_text,
            model=getattr(self, "model", "gpt-4o"),
            key_file=getattr(self, "key_file", "API_Key.txt")
        )

    # ---------- bước 1: CQ answers ----------
    def generate_cq_answers(self):
        if not self.cq_questions:
            raise RuntimeError("Không có câu hỏi CQ nào được tải.")

        prompt_text = Prompt(
            task_description=f"Trả lời {len(self.cq_questions)} Competency Questions (CQ).",
            context=self.user_desc,
            input_data=self.raw_text,
            goal=f"Trả lời {len(self.cq_questions)} CQ (mục đích KG: {self.kg_purpose}).",
            output_format=f"Đúng định dạng:\n" + "\n".join([f"CQ{i+1}: ..." for i in range(len(self.cq_questions))]),
            constraints="Không thêm lời dẫn, ký tự lạ."
        ).build() + "\n\n[CÁC CÂU HỎI]\n" + "\n".join(self.cq_questions)

        self.cq_answers = self._call_ai(prompt_text)
        # --- Tách câu trả lời theo từng CQ bằng regex ---
        pattern = r"(CQ\d+:\s)"
        parts = re.split(pattern, self.cq_answers)
        cq_dict = {}
        for i in range(1, len(parts), 2):
            key = parts[i].strip()  # CQ1:
            val = parts[i + 1].strip() if i + 1 < len(parts) else ""
            cq_dict[key] = val

        # --- Lưu ra file trong thư mục output ---
        os.makedirs(self.DEFAULT_OUTPUT_FOLDER, exist_ok=True)
        with open(os.path.join(self.DEFAULT_OUTPUT_FOLDER, "cq_answers.txt"), "w", encoding="utf-8") as f:
            for i in range(1, len(self.cq_questions) + 1):
                key = f"CQ{i}"
                question = self.cq_questions[i - 1] if i - 1 < len(self.cq_questions) else "Câu hỏi không rõ"
                answer = cq_dict.get(f"{key}:", "[Không có câu trả lời]")
                f.write(f"{question}\n{answer}\n\n")

        return self.cq_answers

    # ---------- bước 2: seed ontology ----------
    def generate_seed_ontology(self):
        if not self.cq_answers:
            raise RuntimeError("Chưa có câu trả lời CQ.")

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

        # Lưu và `trả về seed ontology
        self.seed_onto = "\n".join(seed_onto_lines)
        return self.seed_onto

    # ---------- phase 1: Class ----------
    def generate_classes(self):
        if self.class_text is not None:
            return self.class_text
        # Combine CQ questions and answers for context
        cq_context = "\n".join([f"{q}\n{a}" for q, a in zip(self.cq_questions, 
            [self.cq_answers.split(f"CQ{i}:")[1].split("CQ")[0].strip() if f"CQ{i}:" in self.cq_answers else "[Không có câu trả lời]" for i in range(1, len(self.cq_questions) + 1)])])
        prompt = Prompt(
            task_description=f"Tạo danh sách các lớp (classes) dựa trên câu trả lời {len(self.cq_questions)} CQ. Lưu ý rằng các lớp này là các lớp trừu tượng, tổng quan không dùng các tên riêng để đặt tên.",
            context=f"Bối cảnh: {self.user_desc}\n\nCâu hỏi và trả lời CQ:\n{cq_context}",
            input_data=self.raw_text,
            goal="Liệt kê các lớp, mỗi dòng ở dạng '- id: ... | label: ...' (id là tên PascalCase tiếng Việt không dấu, label là tên đầy đủ có dấu).",
            output_format="Ví dụ:\n- id: QuocHieu | label: Quốc Hiệu\n- id: Nguoi | label: Người",
            constraints="CHỈ trả về danh sách, KHÔNG thêm giải thích, ví dụ, lời dẫn, kết luận. Không thêm bất kỳ dòng nào ngoài kết quả theo format yêu cầu."
        ).build()
        self.class_text = self._call_ai(prompt)
        return self.class_text

    # ---------- phase 2: DatatypeProperty ----------
    def generate_properties(self):
        if self.prop_text is not None:
            return self.prop_text
        # Combine CQ questions and answers for context
        cq_context = "\n".join([f"{q}\n{a}" for q, a in zip(self.cq_questions, 
            [self.cq_answers.split(f"CQ{i}:")[1].split("CQ")[0].strip() if f"CQ{i}:" in self.cq_answers else "[Không có câu trả lời]" for i in range(1, len(self.cq_questions) + 1)])])
        prompt = Prompt(
            task_description=f"Tạo thuộc tính dữ liệu (datatype properties) cho các lớp dựa trên câu trả lời {len(self.cq_questions)} CQ.",
            context=f"Danh sách lớp:\n{self.class_text}\n\nCâu hỏi và trả lời CQ:\n{cq_context}",
            input_data=self.raw_text,
            goal="Tạo thuộc tính dữ liệu cho từng lớp, mỗi dòng ở dạng 'class_id: prop_id|label, ...' (prop_id là tên không dấu, label là tiếng Việt đầy đủ).",
            output_format="Ví dụ: Nguoi: ten|Tên, tuoi|Tuổi",
            constraints="CHỈ trả về danh sách, KHÔNG thêm giải thích, ví dụ, lời dẫn, kết luận. Không thêm bất kỳ dòng nào ngoài kết quả theo format yêu cầu."
        ).build()
        self.prop_text = self._call_ai(prompt)
        return self.prop_text

    # ---------- phase 3: ObjectProperty ----------
    def generate_relations(self):
        if self.rel_text is not None:
            return self.rel_text
        # Combine CQ questions and answers for context
        cq_context = "\n".join([f"{q}\n{a}" for q, a in zip(self.cq_questions, 
            [self.cq_answers.split(f"CQ{i}:")[1].split("CQ")[0].strip() if f"CQ{i}:" in self.cq_answers else "[Không có câu trả lời]" for i in range(1, len(self.cq_questions) + 1)])])
        prompt = Prompt(
            task_description=f"Tạo quan hệ (object properties) giữa các lớp dựa trên câu trả lời {len(self.cq_questions)} CQ.",
            context=f"Danh sách lớp:\n{self.class_text}\n\nDanh sách thuộc tính:\n{self.prop_text}\n\nCâu hỏi và trả lời CQ:\n{cq_context}",
            input_data=self.raw_text,
            goal="Tạo quan hệ giữa các lớp, mỗi dòng ở dạng '- id: quanHeId | label: Tên quan hệ | (ClassA_id → ClassB_id)'.",
            output_format="Ví dụ:\n- id: thuocQuocHieu | label: Thuộc Quốc Hiệu | (Nguoi → QuocHieu)",
            constraints="CHỈ trả về danh sách, KHÔNG thêm giải thích, ví dụ, lời dẫn, kết luận. Không thêm bất kỳ dòng nào ngoài kết quả theo format yêu cầu."
        ).build()
        self.rel_text = self._call_ai(prompt)
        return self.rel_text

    # ---------- build OWL ----------
    @staticmethod
    def parse_id_label(line):
        # line: "- id: QuocHieu | label: Quốc Hiệu"
        match = re.match(r"-?\s*id:\s*([^\|]+)\|\s*label:\s*(.+)", line)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None, None

    def build_owl_and_check(self, owl_file="seed_ontology.owl", ns="http://example.org/seed.owl#", run_reasoner=True):
        # Ensure output folder exists
        os.makedirs(self.DEFAULT_OUTPUT_FOLDER, exist_ok=True)
        owl_file_path = os.path.join(self.DEFAULT_OUTPUT_FOLDER, owl_file)

        # Parse classes
        class_map = {}
        for l in self.class_text.splitlines():
            if "id:" in l and "label:" in l:
                cid, clabel = self.parse_id_label(l)
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

        onto.save(file=owl_file_path, format="rdfxml")
        self.owl_path = owl_file_path
        if run_reasoner:
            with onto:
                sync_reasoner_pellet(infer_property_values=True)
        print("✅ Đã lưu OWL:", owl_file_path)
        return True

    # ---------- run full ----------
    def run_Seeding(self):
        print(f"▶️ Trả lời {len(self.cq_questions)} CQ …")
        print(self.generate_cq_answers())
        print("\n▶️ Sinh Seed‑Ontology …")
        print(self.generate_seed_ontology())
        print("\n▶️ Chuyển sang OWL & kiểm tra HermiT/Pellet …")
        self.build_owl_and_check()

    def update_ontology_from_text(self, new_text, owl_file="seed_ontology.owl"):
        """
        Cập nhật ontology hiện tại với các class, properties, và relations mới dựa trên văn bản đầu vào.
        
        Args:
            new_text (str): Văn bản mới để phân tích.
            owl_file (str): Đường dẫn tới file OWL hiện tại.
        """
        # Lưu văn bản mới
        self.set_input_text(new_text)

        # Tạo CQ answers nếu cần (có thể tái sử dụng hoặc tạo mới dựa trên text mới)
        if not self.cq_answers:
            self.generate_cq_answers()

        # Tạo classes mới
        new_class_text = self.generate_classes()
        new_prop_text = self.generate_properties()
        new_rel_text = self.generate_relations()

        # Load ontology hiện tại
        ns = "http://example.org/seed.owl#"
        onto = get_ontology(f"file://{self.owl_path or owl_file}").load()

        # Parse và thêm classes mới
        with onto:
            existing_classes = {cls.name for cls in onto.classes()}
            for line in new_class_text.splitlines():
                if "id:" in line and "label:" in line:
                    cid, clabel = self.parse_id_label(line)
                    if cid and cid not in existing_classes:
                        owl_cls = types.new_class(cid, (Thing,))
                        owl_cls.label = clabel

            # Parse và thêm datatype properties mới
            existing_props = {prop.name for prop in onto.data_properties()}
            for line in new_prop_text.splitlines():
                if ":" in line:
                    class_id, props = line.split(":", 1)
                    class_id = class_id.strip()
                    if class_id in [cls.name for cls in onto.classes()]:
                        pairs = [p.strip() for p in props.split(",") if "|" in p]
                        for pid, plabel in [(p.split("|")[0].strip(), p.split("|")[1].strip()) for p in pairs]:
                            if pid not in existing_props:
                                dp = types.new_class(pid, (DataProperty,))
                                dp.domain = [onto[class_id]]
                                dp.range = [str]
                                dp.label = plabel

            # Parse và thêm object properties mới
            existing_rels = {prop.name for prop in onto.object_properties()}
            for line in new_rel_text.splitlines():
                m = re.match(r"-?\s*id:\s*([^\|]+)\|\s*label:\s*([^\|]+)\|\s*\((.+?)\s*→\s*(.+?)\)", line)
                if m:
                    rel_id, rel_label, dom_id, rng_id = m.groups()
                    if (rel_id not in existing_rels and 
                        dom_id in [cls.name for cls in onto.classes()] and 
                        rng_id in [cls.name for cls in onto.classes()]):
                        op = types.new_class(rel_id.strip(), (ObjectProperty,))
                        op.domain = [onto[dom_id.strip()]]
                        op.range = [onto[rng_id.strip()]]
                        op.label = rel_label.strip()

        # Lưu ontology cập nhật
        os.makedirs(self.DEFAULT_OUTPUT_FOLDER, exist_ok=True)
        owl_file_path = os.path.join(self.DEFAULT_OUTPUT_FOLDER, owl_file)
        onto.save(file=owl_file_path, format="rdfxml")
        self.owl_path = owl_file_path
        print(f"✅ Đã cập nhật ontology tại: {owl_file_path}")
        return True

    # ---------- lưu trạng thái ----------
    def save_state(self, folder_path=DEFAULT_OUTPUT_FOLDER):
        os.makedirs(folder_path, exist_ok=True)
        with open(os.path.join(folder_path, "cq_answers.txt"), "w", encoding="utf-8") as f:
            f.write(self.cq_answers or "")
        with open(os.path.join(folder_path, "seed_ontology.txt"), "w", encoding="utf-8") as f:
            f.write(self.seed_onto or "")
        if self.owl_path:
            owl_dst = os.path.join(folder_path, os.path.basename(self.owl_path))
            if self.owl_path != owl_dst:
                os.replace(self.owl_path, owl_dst)
                self.owl_path = owl_dst
        print(f"✅ Đã lưu CQ, Seed-Ontology, OWL vào thư mục: {folder_path}")

    # ---------- tải lại trạng thái ----------
    def load_state(self, folder_path=DEFAULT_OUTPUT_FOLDER):
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