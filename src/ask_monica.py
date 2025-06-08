# File: src/ask_monica.py
import requests
import json
import logging
from typing import Optional
import os # Đảm bảo os được import

# --- Định nghĩa FallbackSettings ở phạm vi module ---
# Điều này giải quyết lỗi NameError khi config.settings import thành công.
class FallbackSettings:
    MONICA_API_KEY = None
    MONICA_API_ENDPOINT = "https://openapi.monica.im/v1/chat/completions"
    DEFAULT_MONICA_MODEL = "gpt-4o"
    DEFAULT_MONICA_TEMPERATURE = 0.7
    DEFAULT_MONICA_STREAM = False
    DEFAULT_MONICA_TIMEOUT = 30
    # Đường dẫn log mặc định cho fallback
    MONICA_OPERATIONAL_LOG_FILE = "monica_operational_fallback.log" # Sẽ được tạo ở thư mục chạy script
    MONICA_QA_LOG_FILE = "monica_qa_fallback.log" # Sẽ được tạo ở thư mục chạy script
    # Cấp độ log mặc định cho fallback
    MONICA_OPERATIONAL_LOG_LEVEL = "INFO"
    MONICA_QA_LOG_LEVEL = "INFO"

# Cố gắng import settings từ config, nếu thất bại, sử dụng FallbackSettings
try:
    from config import settings
except ImportError:
    # Sử dụng print cho thông báo lỗi ban đầu này vì logger có thể chưa được thiết lập
    print("CRITICAL: Không tìm thấy module config.settings. "
          "Sử dụng FallbackSettings với các giá trị mặc định cứng. "
          "Điều này không được khuyến khích cho môi trường production.")
    settings = FallbackSettings() # Gán một instance của FallbackSettings


# --- Khởi tạo hai loggers ---
op_logger = logging.getLogger(f"{__name__}.operational")
qa_logger = logging.getLogger(f"{__name__}.qa")

# --- Tự cấu hình Logging cho module này ---
# Hàm này sẽ được gọi để thiết lập handlers nếu chúng chưa tồn tại.
def _setup_loggers_if_not_configured():
    # Lấy đường dẫn và cấp độ log từ settings, có fallback nếu thuộc tính không tồn tại
    # getattr(object, name, default)
    op_log_path = getattr(settings, 'MONICA_OPERATIONAL_LOG_FILE', FallbackSettings.MONICA_OPERATIONAL_LOG_FILE)
    qa_log_path = getattr(settings, 'MONICA_QA_LOG_FILE', FallbackSettings.MONICA_QA_LOG_FILE)
    
    op_log_level_str = getattr(settings, 'MONICA_OPERATIONAL_LOG_LEVEL', FallbackSettings.MONICA_OPERATIONAL_LOG_LEVEL).upper()
    qa_log_level_str = getattr(settings, 'MONICA_QA_LOG_LEVEL', FallbackSettings.MONICA_QA_LOG_LEVEL).upper()

    op_log_level = getattr(logging, op_log_level_str, logging.INFO)
    qa_log_level = getattr(logging, qa_log_level_str, logging.INFO)

    # Định dạng formatter
    op_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    qa_formatter = logging.Formatter('%(asctime)s | %(message)s') # Định dạng đơn giản cho Q&A

    # Cấu hình op_logger nếu chưa có handlers
    if not op_logger.handlers:
        op_logger.setLevel(op_log_level)
        op_logger.propagate = False # Quan trọng: tránh log bị lặp lại

        op_file_created = False
        # File Handler cho op_logger
        try:
            # Đảm bảo thư mục chứa file log tồn tại (chỉ cho trường hợp không phải fallback mặc định)
            if op_log_path != FallbackSettings.MONICA_OPERATIONAL_LOG_FILE: # Nếu không phải là fallback path mặc định
                os.makedirs(os.path.dirname(op_log_path), exist_ok=True)

            op_file_handler = logging.FileHandler(op_log_path, encoding='utf-8')
            op_file_handler.setFormatter(op_formatter)
            op_logger.addHandler(op_file_handler)
            op_file_created = True
        except Exception as e:
            # Dùng print vì đây là lỗi setup logger nghiêm trọng
            print(f"CRITICAL SETUP ERROR (op_logger file handler): {e}. Path: {op_log_path}")
        
        # Console Handler cho op_logger
        op_console_handler = logging.StreamHandler()
        op_console_handler.setFormatter(op_formatter)
        op_logger.addHandler(op_console_handler)
        
        # Log một lần sau khi cấu hình xong
        log_msg_op = (f"Operational Logger (op_logger) configured. Level: {op_log_level_str}. "
                      f"File: {op_log_path if op_file_created else 'FAILED/None'}.")
        # Nếu settings là FallbackSettings và file log fallback không tạo được, không nên log vào file đó
        if not (isinstance(settings, FallbackSettings) and not op_file_created):
             op_logger.info(log_msg_op)
        else: # Log ra console nếu là FallbackSettings và file log không tạo được
            print(f"INFO (op_logger fallback): {log_msg_op}")


    # Cấu hình qa_logger nếu chưa có handlers
    if not qa_logger.handlers:
        qa_logger.setLevel(qa_log_level)
        qa_logger.propagate = False

        qa_file_created = False
        # File Handler cho qa_logger
        try:
            if qa_log_path != FallbackSettings.MONICA_QA_LOG_FILE:
                 os.makedirs(os.path.dirname(qa_log_path), exist_ok=True)

            qa_file_handler = logging.FileHandler(qa_log_path, encoding='utf-8')
            qa_file_handler.setFormatter(qa_formatter)
            qa_logger.addHandler(qa_file_handler)
            qa_file_created = True
            # Log vào op_logger về việc qa_logger được cấu hình (nếu op_logger hoạt động)
            op_logger.info(f"Q&A Logger (qa_logger) configured. Level: {qa_log_level_str}. File: {qa_log_path}.")
        except Exception as e:
            print(f"CRITICAL SETUP ERROR (qa_logger file handler): {e}. Path: {qa_log_path}")
            # Ghi lỗi này vào op_logger nếu có thể, hoặc print
            if op_logger.handlers:
                op_logger.error(f"Failed to create file handler for qa_logger at {qa_log_path}: {e}", exc_info=True)
            else:
                print(f"ERROR (op_logger not available): Failed to create file handler for qa_logger at {qa_log_path}: {e}")


_setup_loggers_if_not_configured() # Gọi hàm để cấu hình loggers ngay khi module được import

# --- Hàm chính ask_monica ---
def ask_monica(
    prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    stream: Optional[bool] = None,
    timeout: Optional[int] = None
) -> Optional[str]:
    """
    Gửi prompt tới Monica API và trả về phản hồi.
    Log thông tin vận hành và Q&A vào các file riêng đã được cấu hình.
    """
    api_key = settings.MONICA_API_KEY
    endpoint = settings.MONICA_API_ENDPOINT

    current_model = model if model is not None else settings.DEFAULT_MONICA_MODEL
    current_temperature = temperature if temperature is not None else settings.DEFAULT_MONICA_TEMPERATURE
    current_stream = stream if stream is not None else settings.DEFAULT_MONICA_STREAM
    current_timeout = timeout if timeout is not None else settings.DEFAULT_MONICA_TIMEOUT

    if not api_key:
        op_logger.error("❌ MONICA_API_KEY chưa được cấu hình. Không thể gửi yêu cầu.")
        qa_logger.error(f"PROMPT ATTEMPT FAILED (Missing API Key):\n{prompt.strip()}\n====================\n")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": current_model,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "temperature": current_temperature,
        "stream": current_stream
    }

    op_logger.info(f"Đang gửi yêu cầu tới Monica API. Model: {current_model}, Endpoint: {endpoint}")
    # Tránh log toàn bộ key, chỉ log một phần hoặc thông tin không nhạy cảm
    auth_header_preview = headers.get("Authorization", "No Auth Header")
    if auth_header_preview.startswith("Bearer sk-"): # Monica keys often start with sk-
        auth_header_preview = auth_header_preview[:15] + "..." # Bearer sk-xxxx...
    op_logger.debug(f"Headers (Authorization preview): {auth_header_preview}")
    op_logger.debug(f"Prompt (đầu): {prompt[:100].strip()}...")
    op_logger.debug(f"Data: {json.dumps(data, indent=2)}")


    reply_content: Optional[str] = None
    try:
        response = requests.post(endpoint, headers=headers, json=data, timeout=current_timeout)
        response.raise_for_status()
        result = response.json()
        op_logger.debug(f"Phản hồi JSON từ API: {result}")

        choices = result.get("choices")
        if choices and isinstance(choices, list) and len(choices) > 0:
            message = choices[0].get("message")
            if message and isinstance(message, dict) and "content" in message:
                reply_content = str(message["content"]).strip()
                op_logger.info(f"Nhận được phản hồi thành công từ Monica. Độ dài: {len(reply_content)}")
            else:
                op_logger.warning("Phản hồi API không có 'content' trong 'message.choices[0]'. Response: %s", result)
        else:
            op_logger.warning("Phản hồi API không có 'choices' hoặc 'choices' rỗng/sai định dạng. Response: %s", result)

    except requests.exceptions.HTTPError as http_err:
        error_context = getattr(http_err.response, 'text', 'Không có nội dung response text.')
        op_logger.error(f"Lỗi HTTP khi gọi Monica API: {http_err}. Phản hồi: {error_context}", exc_info=True)
    except requests.exceptions.Timeout as timeout_err:
        op_logger.error(f"Timeout ({current_timeout}s) khi gọi Monica API: {timeout_err}", exc_info=True)
    except requests.exceptions.RequestException as req_err: # Bao gồm ConnectionError, etc.
        op_logger.error(f"Lỗi Request (mạng, DNS, etc.) khi gọi Monica API: {req_err}", exc_info=True)
    except json.JSONDecodeError as json_err:
        response_text = getattr(locals().get('response'), 'text', 'Không có đối tượng response hoặc text.')
        op_logger.error(f"Lỗi giải mã JSON từ Monica API: {json_err}. Response text: '{response_text}'", exc_info=True)
    except Exception as e: # Bắt các lỗi không lường trước khác
        op_logger.error(f"Lỗi không xác định khi xử lý yêu cầu tới Monica API: {e}", exc_info=True)
    
    # --- Ghi log Q&A ---
    prompt_to_log = prompt.strip()
    if reply_content:
        reply_to_log = reply_content.strip()
        qa_logger.info(f"PROMPT:\n{prompt_to_log}\n--------------------\nRESPONSE:\n{reply_to_log}\n====================\n")
    else:
        qa_logger.warning(f"PROMPT:\n{prompt_to_log}\n--------------------\nRESPONSE: [NO VALID CONTENT OR ERROR OCCURRED - Check operational log for details]\n====================\n")

    return reply_content

# --- Khối if __name__ == '__main__': để test nhanh ---
if __name__ == '__main__':
    # Logging đã được cấu hình bởi _setup_loggers_if_not_configured() ở trên
    op_logger.info("Chạy ask_monica.py như một script độc lập để test.")

    if not settings.MONICA_API_KEY:
        op_logger.critical("MONICA_API_KEY is NOT SET. Standalone test will likely fail to make API calls.")
        print("CRITICAL: MONICA_API_KEY is not set in .env or settings. Please configure it to test API calls.")
    
    # Test với API Key (nếu có)
    if settings.MONICA_API_KEY:
        test_prompt_success = "Kể một câu chuyện cười về một con robot."
        op_logger.info(f"Thử gửi test prompt (thành công dự kiến): '{test_prompt_success}'")
        response = ask_monica(test_prompt_success)
        if response:
            print("\n--- Phản hồi từ Monica (Test thành công) ---")
            print(response) # In ra console
        else:
            print("\n--- Test thành công không nhận được phản hồi hoặc có lỗi. Kiểm tra logs. ---") # In ra console
    
    # Test trường hợp API key tạm thời bị xóa (mô phỏng lỗi)
    op_logger.info("Thử nghiệm trường hợp MONICA_API_KEY bị thiếu (tạm thời).")
    original_key_for_test = settings.MONICA_API_KEY
    settings.MONICA_API_KEY = None # Tạm thời xóa key
    test_prompt_no_key = "Prompt này sẽ thất bại do thiếu API key."
    ask_monica(test_prompt_no_key)
    settings.MONICA_API_KEY = original_key_for_test # Khôi phục key
    op_logger.info("Đã khôi phục MONICA_API_KEY (nếu có). Kết thúc test standalone.")