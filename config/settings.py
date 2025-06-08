# config/settings.py

import os
from dotenv import load_dotenv
import logging # Cần thiết nếu bạn muốn sử dụng các hằng số logging.<LEVEL>

# Tải các biến từ file .env vào môi trường
# Giả sử .env ở thư mục gốc của dự án (một cấp trên thư mục 'config')
# Ví dụ: SOURCE/.env
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Monica API Settings ---
MONICA_API_ENDPOINT = os.getenv("MONICA_API_ENDPOINT", "https://openapi.monica.im/v1/chat/completions")
MONICA_API_KEY = os.getenv("MONICA_API_KEY")
DEFAULT_MONICA_MODEL = os.getenv("DEFAULT_MODEL_NAME", "gpt-4o")
DEFAULT_MONICA_TEMPERATURE = float(os.getenv("DEFAULT_MONICA_TEMPERATURE", "0.7"))
DEFAULT_MONICA_STREAM = os.getenv("DEFAULT_MONICA_STREAM", "False").lower() in ('true', '1', 't')
DEFAULT_MONICA_TIMEOUT = int(os.getenv("DEFAULT_MONICA_TIMEOUT", "60"))

# --- Neo4j Settings ---
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# --- File Paths and Directories ---
# Thư mục gốc của dự án (giả sử settings.py nằm trong config/, và config/ nằm trong SOURCE/)
PROJECT_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT_DIR, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
INPUT_TEXT_DIR = os.path.join(DATA_DIR, "input_text")
CQ_DIR = os.path.join(DATA_DIR, "CQ")

# Tên file chứa câu trả lời cho Critical Questions (CQ)
# File này sẽ được lưu trong OUTPUT_DIR
CQ_ANSWERS_FILENAME = "cq_answers.txt"

# Đảm bảo thư mục output và các thư mục dữ liệu chính tồn tại
try:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(INPUT_TEXT_DIR, exist_ok=True)
    os.makedirs(CQ_DIR, exist_ok=True)
except OSError as e:
    # Sử dụng print vì logger có thể chưa được cấu hình đầy đủ
    print(f"Lỗi khi tạo thư mục dữ liệu hoặc output: {e}. Một số hoạt động có thể không thành công.")

# --- Logging Settings cho Monica (sử dụng trong ask_monica.py) ---
# Log cho vận hành, lỗi, thông tin chung của ask_monica
MONICA_OPERATIONAL_LOG_FILE = os.path.join(OUTPUT_DIR, "monica_operational.log")
MONICA_OPERATIONAL_LOG_LEVEL = os.getenv("MONICA_OPERATIONAL_LOG_LEVEL", "INFO").upper() # DEBUG, INFO, WARNING, ERROR

# Log mới chỉ chứa Prompt và Response (Q&A)
MONICA_QA_LOG_FILE = os.path.join(OUTPUT_DIR, "monica_qa.log")
MONICA_QA_LOG_LEVEL = os.getenv("MONICA_QA_LOG_LEVEL", "INFO").upper() # Thường là INFO cho Q&A

# --- Ontology Settings (sử dụng trong owl_handler.py và các module liên quan) ---
OWL_OUTPUT_DIR = OUTPUT_DIR # Nơi lưu file OWL được tạo ra
DEFAULT_OWL_FILENAME = "generated_ontology.owl" # Tên file OWL mặc định
DEFAULT_ONTOLOGY_NAMESPACE = "http://example.org/ontology#" # Namespace mặc định cho ontology

# --- FAISS Settings (sử dụng trong vn_embedding_search.py) ---
FAISS_VECTOR_DIM = 768 # Kích thước vector của embedding model
FAISS_MODEL_NAME = 'keepitreal/vietnamese-sbert' # Tên model SentenceTransformer
FAISS_INDEX_PATH = os.path.join(PROJECT_ROOT_DIR, "faiss_index.index") # Đường dẫn lưu FAISS index
FAISS_PHRASE_MAP_PATH = os.path.join(PROJECT_ROOT_DIR, "phrase_map.pkl") # Đường dẫn lưu bản đồ cụm từ

# --- CHẾ ĐỘ CHẠY PIPELINE ---
# Lấy chế độ chạy từ biến môi trường, mặc định là 'APPEND' (bổ sung)
# Các giá trị hợp lệ: 'CREATE_NEW', 'APPEND'
PIPELINE_MODE = os.getenv("PIPELINE_MODE", "CREATE_NEW").upper()


# --- Helper function to ensure critical settings are present ---
# Bạn có thể gọi hàm này từ main.py hoặc khi khởi tạo các module cần thiết
def check_critical_settings():
    """Kiểm tra xem các cấu hình quan trọng đã được thiết lập chưa."""
    critical_vars = {
        "MONICA_API_KEY": MONICA_API_KEY,
        "NEO4J_PASSWORD": NEO4J_PASSWORD
    }
    missing = [name for name, val in critical_vars.items() if val is None]
    if missing:
        error_message = (f"Các biến môi trường/cấu hình quan trọng sau chưa được thiết lập: {', '.join(missing)}. "
                         "Vui lòng kiểm tra file .env hoặc cấu hình hệ thống.")
        print(f"ERROR CONFIG: {error_message}")
        raise EnvironmentError(error_message)

# --- Logging thông báo khi load settings ---
# Những print này hữu ích để xác nhận settings đã được load
print("✅ Config settings loaded.")
if MONICA_API_KEY:
    print(f"ℹ️ MONICA_API_KEY is configured. Default Monica Model: {DEFAULT_MONICA_MODEL}")
else:
    print("⚠️ MONICA_API_KEY is NOT configured.")

if NEO4J_PASSWORD:
     print("ℹ️ NEO4J_PASSWORD is configured (Neo4j URI/User might be using defaults).")
else:
    print("⚠️ NEO4J_PASSWORD is NOT configured. Neo4j connection will likely fail.")

print(f"ℹ️ Pipeline Mode: {PIPELINE_MODE}") # Thêm thông báo về chế độ chạy
print(f"ℹ️ Input text is expected in: {INPUT_TEXT_DIR}")
print(f"ℹ️ Output will be generated in: {OUTPUT_DIR}")