import logging
import os
import sys
import re # Added for parsing AI response in the new function
from typing import Optional, List, Dict, Any

# Khởi tạo biến settings ở phạm vi toàn cục, sẽ được gán sau
settings = None

try:
    from config import settings as loaded_settings
    settings = loaded_settings

    if not hasattr(settings, 'OUTPUT_DIR'):
        print("LỖI NGHIÊM TRỌNG: Thuộc tính 'OUTPUT_DIR' không được định nghĩa trong 'config.settings'. "
              "Vui lòng kiểm tra file cấu hình settings.py. Dừng chương trình.")
        sys.exit(1)

    if not hasattr(settings, 'CQ_ANSWERS_FILENAME'):
        print("CẢNH BÁO: Thuộc tính 'CQ_ANSWERS_FILENAME' không được định nghĩa trong 'config.settings'. "
              "Sử dụng giá trị mặc định là 'cq_answers.txt'.")
        setattr(settings, 'CQ_ANSWERS_FILENAME', "cq_answers.txt")

except ImportError:
    print("LỖI NGHIÊM TRỌNG: Không tìm thấy module 'config.settings'. "
          "Hãy đảm bảo file 'config/settings.py' tồn tại và thư mục 'config' là một package "
          "(nghĩa là có file __init__.py bên trong). "
          "Ngoài ra, hãy đảm bảo bạn đang chạy script từ thư mục gốc của dự án (thư mục SOURCE). "
          "Dừng chương trình.")
    sys.exit(1)
except AttributeError as e:
    print(f"LỖI NGHIÊM TRỌNG: Có lỗi với cấu trúc hoặc thuộc tính trong 'config.settings': {e}. "
          "Dừng chương trình.")
    sys.exit(1)

from .prompt_builder import Prompt
from .ask_monica import ask_monica

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.propagate = False


class ContextBuilder:
    def __init__(self, project_description: str, project_goal: str):
        if not project_description or not project_goal:
            error_msg = "Mô tả dự án và mục tiêu dự án không được để trống."
            logger.error(error_msg)
            raise ValueError(error_msg)

        self.project_description: str = project_description
        self.project_goal: str = project_goal
        self.cq_answers_file_path: str = os.path.join(settings.OUTPUT_DIR, settings.CQ_ANSWERS_FILENAME)
        self.project_context_summary: Optional[str] = None # Khởi tạo thuộc tính

        if os.path.exists(self.cq_answers_file_path):
            try:
                os.remove(self.cq_answers_file_path)
                logger.info(f"Đã xóa file câu trả lời CQ cũ: {self.cq_answers_file_path}")
            except OSError as e:
                logger.error(f"Không thể xóa file câu trả lời CQ cũ '{self.cq_answers_file_path}': {e}")

        logger.info(f"ContextBuilder đã được khởi tạo cho dự án: '{project_goal}'")
        logger.debug(f"Mô tả dự án: {self.project_description}")
        logger.info(f"File câu trả lời Competency Questions (CQ) sẽ được lưu tại: {self.cq_answers_file_path}")

    def _read_file_content(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Lỗi: Không tìm thấy file '{file_path}'.")
            return None
        except Exception as e:
            logger.error(f"Lỗi khi đọc file '{file_path}': {e}", exc_info=True)
            return None

    def _save_single_cq_response(self, all_questions_str: str, combined_answer: str) -> None:
        """Ghi toàn bộ khối câu hỏi và câu trả lời tổng hợp vào file."""
        try:
            # Không tạo thư mục mới, giả định settings.OUTPUT_DIR đã tồn tại
            os.makedirs(settings.OUTPUT_DIR, exist_ok=True) # Đảm bảo thư mục output tồn tại
            with open(self.cq_answers_file_path, 'w', encoding='utf-8') as f: # Sử dụng 'w' để ghi mới
                f.write("TOÀN BỘ CÁC CÂU HỎI COMPETENCY QUESTIONS (CQ):\n")
                f.write(all_questions_str.strip() + "\n\n")
                f.write("TRẢ LỜI TỔNG HỢP TỪ AI:\n")
                f.write(combined_answer.strip() + "\n")
                f.write("---\n")
            logger.info(f"Đã ghi toàn bộ Q&A vào '{self.cq_answers_file_path}'.")
        except Exception as e:
            logger.error(f"Lỗi khi ghi vào file '{self.cq_answers_file_path}': {e}", exc_info=True)

    def build_run_cq_answers(self, cq_questions_path: str, initial_input_text_path: Optional[str]) -> bool:
        logger.info(f"Bắt đầu quá trình build_run_cq_answers với file câu hỏi: '{cq_questions_path}' và file input: '{initial_input_text_path}'.")

        cq_questions_content = self._read_file_content(cq_questions_path)
        if cq_questions_content is None:
            logger.error("Không thể tiếp tục build_run_cq_answers do không đọc được file câu hỏi.")
            return False
        
        initial_input_content = ""
        if initial_input_text_path:
            temp_content = self._read_file_content(initial_input_text_path)
            if temp_content is None:
                logger.warning(f"Không đọc được file initial input '{initial_input_text_path}', CQ sẽ được trả lời mà không có nội dung tham khảo này.")
            else:
                initial_input_content = temp_content
        else:
            logger.info("Không có initial_input_text_path được cung cấp, CQ sẽ được trả lời dựa trên mô tả/mục tiêu dự án (nếu có trong prompt).")


        questions = [q.strip() for q in cq_questions_content.splitlines() if q.strip()]
        if not questions:
            logger.warning("Không tìm thấy câu hỏi nào trong file CQ_questions.")
            return True # Coi như thành công nếu không có câu hỏi để xử lý

        logger.info(f"Đã đọc được {len(questions)} câu hỏi CQ.")

        all_questions_str = "\n".join(questions)
        
        logger.info("Đang xử lý tất cả các câu hỏi CQ một lần...")

        prompt_obj = Prompt(
            task_description="Dựa vào mô tả dự án, mục tiêu dự án và nội dung tài liệu được cung cấp (nếu có), hãy lần lượt trả lời tất cả các câu hỏi được liệt kê dưới đây một cách chi tiết và đầy đủ nhất có thể cho từng câu hỏi. Trình bày rõ ràng câu hỏi và câu trả lời tương ứng.",
            context=f"Mô tả dự án: {self.project_description}\nMục tiêu dự án: {self.project_goal}",
            input_data=f"Nội dung tài liệu tham khảo (nếu có):\n{initial_input_content}" if initial_input_content else "Không có nội dung tài liệu tham khảo bổ sung.",
            goal=f"Các câu hỏi cần trả lời lần lượt:\n{all_questions_str}",
            output_format=f"Đúng định dạng:\n" + "\n".join([f"CQ{i+1}: [Câu trả lời cho CQ{i+1}]" for i in range(len(questions))]),
            constraints="Không thêm lời dẫn, ký tự lạ. Trả lời đầy đủ cho từng câu hỏi."
        )
        final_prompt = prompt_obj.build()
        logger.debug(f"Prompt tổng hợp được xây dựng (đầu):\n{final_prompt[:500]}...")

        combined_ai_answer = ask_monica(prompt=final_prompt)

        if combined_ai_answer is None:
            logger.warning("Không nhận được câu trả lời từ AI cho khối câu hỏi.")
            combined_ai_answer = "[Không nhận được phản hồi từ AI cho toàn bộ khối câu hỏi]"
        else:
            logger.info("Nhận được câu trả lời tổng hợp từ AI cho các câu hỏi CQ.")
        
        self._save_single_cq_response(all_questions_str, combined_ai_answer)

        logger.info(f"Hoàn tất việc xử lý các câu hỏi CQ. Kết quả đã được lưu vào '{self.cq_answers_file_path}'.")
        return True

    def generate_project_context_from_cq_answers(
        self,
        project_description: str,
        project_goal: str
    ) -> Optional[str]:
        """
        Đọc nội dung từ file cq_answers.txt, gửi đến AI để tóm tắt thành một đoạn context mô tả dự án,
        sử dụng PromptBuilder để tạo prompt, và lưu kết quả context vào file project_context.txt.
        """
        if not hasattr(settings, 'OUTPUT_DIR') or not hasattr(settings, 'CQ_ANSWERS_FILENAME'):
            logger.error("Lỗi: settings.OUTPUT_DIR hoặc settings.CQ_ANSWERS_FILENAME chưa được cấu hình.")
            return None
        
        if not os.path.exists(self.cq_answers_file_path):
            logger.error(f"Lỗi: Không tìm thấy file '{self.cq_answers_file_path}'. "
                        "Hãy đảm bảo file này được tạo ra từ bước trả lời CQ trước đó.")
            return None

        logger.info(f"Đang đọc nội dung từ file: {self.cq_answers_file_path}")
        cq_answers_content = self._read_file_content(self.cq_answers_file_path)

        if not cq_answers_content or not cq_answers_content.strip():
            logger.warning(f"File '{self.cq_answers_file_path}' rỗng hoặc chỉ chứa khoảng trắng. "
                        "Không thể tạo context. Sẽ thử tạo context chỉ dựa trên mô tả và mục tiêu dự án.")
            # Fallback: Tạo context chỉ từ mô tả và mục tiêu dự án nếu file CQ rỗng
            prompt_generator = Prompt(
                task_description=(
                    "Dựa vào Mô tả dự án và Mục tiêu dự án được cung cấp, "
                    "hãy viết một đoạn văn ngắn (khoảng 3-5 câu) để làm 'Bối cảnh tổng quan của dự án'."
                ),
                context=(
                    f"Thông tin nền tảng về dự án:\n"
                    f"1. Mô tả dự án ban đầu: {project_description}\n"
                    f"2. Mục tiêu dự án ban đầu: {project_goal}"
                ),
                input_data="Không có nội dung Q&A chi tiết để tham khảo.",
                goal=(
                    "Tạo ra một đoạn context tổng quan, súc tích, mạch lạc. "
                    "Đoạn context này cần mô tả rõ ràng về chủ đề chính, mục đích, và phạm vi của dự án."
                ),
                instructions=(
                    "Đoạn văn này sẽ được sử dụng làm context chung cho các prompt khác trong hệ thống. "
                    "Tập trung vào việc tổng hợp thông tin từ mô tả và mục tiêu đã cho."
                ),
                output_format="Một đoạn văn duy nhất, không có tiêu đề hay định dạng phức tạp."
            )
        else:
            logger.info("Đã đọc xong nội dung cq_answers.txt. Chuẩn bị gọi AI để tạo context mô tả dự án.")
            prompt_generator = Prompt(
                task_description=(
                    "Dựa vào các thông tin được cung cấp (Mô tả dự án, Mục tiêu dự án, và đặc biệt là Nội dung Q&A), "
                    "hãy viết một đoạn văn ngắn (khoảng 3-5 câu) để làm 'Bối cảnh tổng quan của dự án'."
                ),
                context=(
                    f"Thông tin nền tảng về dự án:\n"
                    f"1. Mô tả dự án ban đầu: {project_description}\n"
                    f"2. Mục tiêu dự án ban đầu: {project_goal}"
                ),
                input_data=(
                    f"Nội dung Q&A (trích từ file '{settings.CQ_ANSWERS_FILENAME}') để tham khảo chính:\n"
                    f"{cq_answers_content}"
                ),
                goal=(
                    "Tạo ra một đoạn context tổng quan, súc tích, mạch lạc. "
                    "Đoạn context này cần mô tả rõ ràng về chủ đề chính, mục đích, phạm vi và cách thức hoạt động/xử lý thông tin cốt lõi của dự án."
                ),
                instructions=(
                    "Đoạn văn này sẽ được sử dụng làm context chung cho các prompt khác trong hệ thống, "
                    "giúp AI hiểu rõ hơn về dự án khi thực hiện các tác vụ sau này. "
                    "Tập trung vào việc tổng hợp thông tin để cung cấp bối cảnh cần thiết cho AI."
                ),
                output_format="Một đoạn văn duy nhất, không có tiêu đề hay định dạng phức tạp."
            )

        final_prompt_text = prompt_generator.build()
        logger.debug(f"Prompt gửi đến AI để tạo context (sử dụng PromptBuilder) (đầu):\n{final_prompt_text[:500]}...")

        project_context_str = ask_monica(prompt=final_prompt_text)

        if project_context_str:
            project_context_str = project_context_str.strip()
            logger.info("AI đã tạo thành công context mô tả dự án.")
            logger.debug(f"Context được tạo:\n{project_context_str}")

            project_context_filename = getattr(settings, 'PROJECT_CONTEXT_FILENAME', "project_context.txt") #
            project_context_file_path = os.path.join(settings.OUTPUT_DIR, project_context_filename)

            try:
                os.makedirs(settings.OUTPUT_DIR, exist_ok=True) # Đảm bảo thư mục output tồn tại
                with open(project_context_file_path, 'w', encoding='utf-8') as f:
                    f.write(project_context_str)
                logger.info(f"Đã lưu context dự án vào file: '{project_context_file_path}'")
            except Exception as e:
                logger.error(f"Lỗi khi lưu context dự án vào file '{project_context_file_path}': {e}", exc_info=True)
            return project_context_str
        else:
            logger.error("AI không trả về được context mô tả dự án.")
            return None

    def run_pipeline(self, cq_questions_path: Optional[str] = None, initial_input_text_path: Optional[str] = None):
        """
        Thực thi toàn bộ pipeline xây dựng context.
        """
        logger.info("Bắt đầu pipeline xây dựng context...")

        if cq_questions_path and os.path.exists(cq_questions_path):
            logger.info(f"Thực hiện build_run_cq_answers với CQ file: '{cq_questions_path}'.")
            # initial_input_text_path có thể là None, build_run_cq_answers đã xử lý điều này
            cq_success = self.build_run_cq_answers(cq_questions_path, initial_input_text_path)
            if not cq_success:
                logger.error("Bước build_run_cq_answers không thành công. Context có thể không đầy đủ.")
        else:
            logger.warning(f"Không có file CQ hợp lệ ('{cq_questions_path}'), bỏ qua bước build_run_cq_answers. Context sẽ được tạo dựa trên mô tả/mục tiêu dự án (nếu có).")

        logger.info("Thực hiện generate_project_context_from_cq_answers để tạo context mô tả dự án...")
        generated_project_context = self.generate_project_context_from_cq_answers(
            project_description=self.project_description,
            project_goal=self.project_goal
        )

        if generated_project_context:
            self.project_context_summary = generated_project_context
            project_context_filename = getattr(settings, 'PROJECT_CONTEXT_FILENAME', "project_context.txt")
            logger.info(f"Đã tạo và lưu context tổng quan của dự án vào file '{project_context_filename}'. Context cũng đã được lưu vào self.project_context_summary.")
        else:
            self.project_context_summary = None # Đảm bảo là None nếu không tạo được
            logger.warning("Không thể tạo context tổng quan của dự án. File 'project_context.txt' có thể không được tạo/cập nhật.")
        
        logger.info("Pipeline xây dựng context hoàn tất.")

    def extract_information_from_file(self, input_file_path: str) -> Optional[List[str]]:
        """
        Đọc một file văn bản, nạp bối cảnh dự án, và gọi AI để trích xuất thông tin.
        """
        logger.info(f"Bắt đầu trích xuất thông tin từ file: {input_file_path}")

        file_content = self._read_file_content(input_file_path)
        if file_content is None:
            logger.error(f"Không thể đọc nội dung từ file: {input_file_path}. Dừng trích xuất.")
            return None
        if not file_content.strip():
            logger.warning(f"File {input_file_path} rỗng. Không có thông tin để trích xuất.")
            return []

        project_context_text = self.project_context_summary
        if not project_context_text: # Nếu context chưa được tạo từ pipeline hoặc bị lỗi
            project_context_filename = getattr(settings, 'PROJECT_CONTEXT_FILENAME', "project_context.txt")
            project_context_file_path = os.path.join(settings.OUTPUT_DIR, project_context_filename)
            logger.info(f"self.project_context_summary rỗng. Thử đọc từ file: '{project_context_file_path}'")
            project_context_text = self._read_file_content(project_context_file_path)
            if not project_context_text:
                logger.warning(f"Không tìm thấy project_context từ file. Sử dụng context dự phòng.")
                project_context_text = f"Mô tả dự án: {self.project_description}. Mục tiêu: {self.project_goal}" # Context dự phòng cơ bản
            else:
                logger.info("Đã tải project_context từ file để trích xuất thông tin.")
        else:
            logger.info("Sử dụng self.project_context_summary đã có cho trích xuất thông tin.")

        prompt_obj = Prompt(
            task_description="Phân tích và trích xuất các thông tin cốt lõi, quan trọng nhất từ văn bản được cung cấp, dựa trên bối cảnh dự án. Liệt kê các ý chính, sự kiện, nhân vật, địa điểm, khái niệm nổi bật.",
            context=f"Bối cảnh dự án:\n{project_context_text}",
            input_data=f"Nội dung văn bản cần phân tích:\n```text\n{file_content}\n```", #
            goal="Trích xuất một danh sách các mục thông tin quan trọng. Mỗi mục là một ý riêng biệt, ngắn gọn, súc tích nhưng đủ ý.",
            output_format="Một danh sách các mục thông tin. Mỗi mục trên một dòng mới, có thể bắt đầu bằng gạch đầu dòng (-) hoặc số thứ tự (1., 2., ...).",
            constraints="Chỉ trả về danh sách các thông tin. Không thêm lời dẫn, giải thích thừa, hay bất kỳ nội dung nào khác ngoài danh sách. Tập trung vào các chi tiết thực tế, sự kiện, và các đối tượng chính."
        )
        final_prompt = prompt_obj.build()
        logger.debug(f"Prompt gửi đến AI để trích xuất thông tin (đầu):\n{final_prompt[:500]}...")

        ai_response = ask_monica(prompt=final_prompt)

        if ai_response is None:
            logger.error("Không nhận được phản hồi từ AI cho việc trích xuất thông tin.")
            return None
        if not ai_response.strip():
            logger.warning("AI trả về phản hồi rỗng cho trích xuất thông tin.")
            return []

        logger.info("Nhận được phản hồi từ AI. Đang xử lý để tạo danh sách thông tin...")
        extracted_lines = [line.strip() for line in ai_response.splitlines()]
        
        processed_info_list = []
        for line in extracted_lines:
            if not line: continue
            # Regex cải tiến để loại bỏ các loại marker list phổ biến hơn
            match = re.match(r"^\s*(?:[\-\*\+]|(?:[0-9]+[\.\)\-]?)|(?:[a-zA-Z][\.\)\-]?))\s*(.*)", line)
            content = match.group(1).strip() if match else line
            if content:
                processed_info_list.append(content)
        
        final_list = [item for item in processed_info_list if item] # Lọc các chuỗi rỗng cuối cùng

        if not final_list:
            logger.warning(f"AI trả về phản hồi, nhưng không trích xuất được danh sách thông tin hợp lệ. Phản hồi AI: '{ai_response}'")
            return []

        logger.info(f"Đã trích xuất được {len(final_list)} thông tin từ file '{input_file_path}'.")
        return final_list