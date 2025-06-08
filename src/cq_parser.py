# File: src/cq_parser.py (Phiên bản sử dụng AI)
import json
import logging
import re
from typing import List, Dict, Tuple

# Import các module cần thiết từ project
from .ask_monica import ask_monica
from .prompt_builder import Prompt

logger = logging.getLogger(__name__)

# Định nghĩa các lớp cha từ seed_ontology để AI có context
SEED_PARENT_CLASSES = ["ThucThe", "DoiTuong", "SuKien", "TacNhan", "DoiTuongThongTin", "DiaDiem", "KhaiNiem", "ThoiGian"]

def _build_ontology_parsing_prompt(cq_answers_content: str) -> str:
    """Xây dựng prompt chi tiết để yêu cầu AI phân tích và trả về JSON."""
    
    json_structure_example = """
    {
      "classes": [
        {
          "id": "DiTichKhaoCo",
          "label": "Di tích khảo cổ",
          "parent": "DiaDiem"
        }
      ],
      "properties": {
        "DiTichKhaoCo": [
          {
            "id": "coTen",
            "label": "Tên",
            "type": "string"
          }
        ]
      },
      "relations": [
        {
          "id": "chua",
          "label": "chứa",
          "domain": "DiTichKhaoCo",
          "range": "CongCuDa"
        }
      ]
    }
    """

    prompt = Prompt(
        task_description=(
            "Bạn là một kỹ sư ontology chuyên nghiệp. Nhiệm vụ của bạn là đọc và phân tích kỹ lưỡng nội dung được cung cấp, "
            "bao gồm các câu hỏi năng lực (CQ) và câu trả lời của một hệ thống AI, để trích xuất ra một lược đồ (schema) ontology hoàn chỉnh."
        ),
        context=(
            f"Lược đồ này phải kế thừa từ một ontology hạt giống có sẵn. Các lớp cha trong ontology hạt giống là: "
            f"{', '.join(SEED_PARENT_CLASSES)}. Bạn cần ánh xạ các lớp cụ thể bạn tìm thấy (ví dụ: 'Nhà khoa học') "
            f"vào một trong các lớp cha này (ví dụ: 'TacNhan')."
        ),
        input_data=f"Đây là nội dung cần phân tích:\n```text\n{cq_answers_content}\n```",
        goal=(
            "Tạo ra một đối tượng JSON duy nhất, sạch sẽ, không có bất kỳ giải thích hay ký tự thừa nào. "
            "Đối tượng JSON này phải mô tả chính xác các lớp, thuộc tính của từng lớp, và mối quan hệ giữa các lớp dựa trên nội dung đã cho."
        ),
        output_format=(
            f"Chỉ trả về JSON theo đúng cấu trúc sau. Không thêm bất kỳ văn bản nào khác:\n"
            f"```json\n{json_structure_example}\n```"
        ),
        constraints=(
            "ID phải ở định dạng PascalCase cho lớp và quan hệ, camelCase cho thuộc tính. "
            "Luôn xác định 'domain' và 'range' cho mỗi quan hệ. "
            "Mỗi lớp phải có một 'parent' từ danh sách các lớp cha đã cho."
        )
    )
    return prompt.build()

def parse_cq_answers_with_ai(file_path: str) -> Tuple[List[Dict], Dict, List[Dict]]:
    """
    Sử dụng AI để phân tích file cq_answers.txt và trích xuất cấu trúc ontology.
    """
    logger.info("Bắt đầu phân tích ontology bằng AI...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"Không tìm thấy file CQ answers tại: {file_path}")
        return [], {}, []

    if not content.strip():
        logger.warning(f"File '{file_path}' rỗng. Không có gì để phân tích.")
        return [], {}, []

    # Xây dựng và gửi prompt
    prompt_text = _build_ontology_parsing_prompt(content)
    logger.debug(f"Gửi prompt đến AI để phân tích ontology...")
    
    ai_response = ask_monica(prompt=prompt_text)

    if not ai_response:
        logger.error("AI không trả về phản hồi cho việc phân tích ontology.")
        return [], {}, []

    # Xử lý và phân tích phản hồi JSON từ AI
    try:
        # Cố gắng tìm khối JSON trong phản hồi của AI
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if not json_match:
            logger.error("Không tìm thấy đối tượng JSON hợp lệ trong phản hồi của AI.")
            logger.debug(f"Phản hồi AI:\n{ai_response}")
            return [], {}, []
        
        json_data_str = json_match.group(0)
        data = json.loads(json_data_str)
        
        # Trích xuất dữ liệu từ JSON
        class_defs = data.get("classes", [])
        prop_defs = data.get("properties", {})
        rel_defs = data.get("relations", [])
        
        if not (class_defs or prop_defs or rel_defs):
            logger.warning("AI đã trả về JSON nhưng không có định nghĩa nào bên trong.")
            return [], {}, []
            
        logger.info(f"✅ AI đã phân tích thành công: {len(class_defs)} lớp, {len(prop_defs)} nhóm thuộc tính, {len(rel_defs)} quan hệ.")
        return class_defs, prop_defs, rel_defs

    except json.JSONDecodeError as e:
        logger.error(f"Lỗi khi phân tích JSON từ phản hồi của AI: {e}")
        logger.debug(f"Phản hồi AI không hợp lệ:\n{ai_response}")
        return [], {}, []
    except Exception as e:
        logger.error(f"Lỗi không xác định khi xử lý phản hồi từ AI: {e}")
        return [], {}, []

# Đổi tên hàm chính để main.py có thể gọi mà không cần sửa đổi
parse_cq_answers_for_ontology = parse_cq_answers_with_ai