# File: SOURCE/test.py

import logging
import time
import os # Cần thiết để thao tác với settings cho test

# Versuche, Einstellungen zu importieren. Dies sollte nach dem ask_monica-Import erfolgen,
# falls ask_monica das Logging zuerst konfiguriert.
# Es ist jedoch besser, das Logging zentral in main.py oder hier für Tests zu steuern.
try:
    from config import settings
except ImportError as e:
    print(f"LỖI NGHIÊM TRỌNG: Không thể import config.settings: {e}")
    print("Hãy đảm bảo file config/settings.py tồn tại và PYTHONPATH được cấu hình đúng.")
    print("Hoặc bạn đang chạy test.py từ thư mục không phải là thư mục gốc của dự án (SOURCE).")
    exit(1)
# Optional: Gọi hàm kiểm tra cài đặt nếu có và muốn nó chạy trước khi test
# try:
#     if hasattr(settings, 'check_critical_settings'):
#         settings.check_critical_settings()
# except EnvironmentError as e:
#     print(f"Lỗi cấu hình môi trường từ settings.check_critical_settings(): {e}")
#     exit(1)


# Import hàm cần test SAU KHI settings có thể đã được load.
# ask_monica.py sẽ tự cấu hình loggers của nó khi được import.
from src.ask_monica import ask_monica

# --- Cấu hình logging riêng cho file test.py ---
# Logger này dùng để ghi các thông điệp liên quan đến quá trình chạy test.
test_runner_logger = logging.getLogger("TestRunner")
test_runner_logger.propagate = False # Không truyền lên root logger nếu không muốn

if not test_runner_logger.handlers:
    test_runner_logger.setLevel(logging.INFO)
    # Handler cho console
    ch = logging.StreamHandler()
    ch_formatter = logging.Formatter('%(asctime)s - TestRunner - %(levelname)s - %(message)s')
    ch.setFormatter(ch_formatter)
    test_runner_logger.addHandler(ch)
    # Tùy chọn: Handler cho file log riêng của TestRunner
    # test_runner_log_file = os.path.join(settings.OUTPUT_DIR, "test_runner.log")
    # fh = logging.FileHandler(test_runner_log_file, encoding='utf-8')
    # fh.setFormatter(ch_formatter)
    # test_runner_logger.addHandler(fh)
    test_runner_logger.info("TestRunner logger configured.")


def run_test(test_name, test_function, *args, **kwargs):
    """Hàm trợ giúp để chạy một test case và in/log kết quả."""
    print(f"\n================== BẮT ĐẦU TEST: {test_name} ==================")
    test_runner_logger.info(f"--- BẮT ĐẦU TEST: {test_name} ---")
    start_time = time.time()
    result_value = None
    try:
        result_value = test_function(*args, **kwargs)
        if result_value is not None:
            # In một phần kết quả ra console cho dễ theo dõi
            console_output = str(result_value)[:200] + ('...' if len(str(result_value)) > 200 else '')
            print(f"Kết quả test '{test_name}': {console_output}")
            test_runner_logger.info(f"Test '{test_name}' hoàn thành, kết quả (đầu): {console_output}")
        else:
            print(f"Kết quả test '{test_name}': None (Thường là mong đợi cho các kịch bản lỗi)")
            test_runner_logger.info(f"Test '{test_name}' hoàn thành, trả về None.")
    except AssertionError as ae:
        print(f"LỖI ASSERTION trong test '{test_name}': {ae}")
        test_runner_logger.error(f"LỖI ASSERTION trong test '{test_name}': {ae}", exc_info=True)
    except Exception as e:
        print(f"LỖI NGOẠI LỆ không mong muốn trong test '{test_name}': {e}")
        test_runner_logger.error(f"LỖI NGOẠI LỆ không mong muốn trong test '{test_name}': {e}", exc_info=True)
    finally:
        end_time = time.time()
        duration = end_time - start_time
        print(f"================== KẾT THÚC TEST: {test_name} (Thời gian: {duration:.2f}s) ==================")
        test_runner_logger.info(f"--- KẾT THÚC TEST: {test_name} (Thời gian: {duration:.2f}s) ---")
        time.sleep(1) # Tạm dừng ngắn giữa các test để log không bị chồng chéo quá nhanh
    return result_value

# --- Định nghĩa các kịch bản Test ---

def test_successful_call_default_params():
    """Test 1: Gọi API thành công với các tham số mặc định."""
    if not settings.MONICA_API_KEY:
        test_runner_logger.warning("Bỏ qua 'test_successful_call_default_params' do MONICA_API_KEY chưa được cấu hình.")
        print("CẢNH BÁO: MONICA_API_KEY chưa được cấu hình. Bỏ qua test này.")
        return None
    prompt = "Kể một câu chuyện cười ngắn về một con mèo và một con chó."
    response = ask_monica(prompt)
    assert response is not None, "Phản hồi không nên là None cho một cuộc gọi thành công."
    assert len(response) > 0, "Phản hồi không nên rỗng."
    return response

def test_successful_call_custom_params():
    """Test 2: Gọi API thành công với các tham số tùy chỉnh."""
    if not settings.MONICA_API_KEY:
        test_runner_logger.warning("Bỏ qua 'test_successful_call_custom_params' do MONICA_API_KEY chưa được cấu hình.")
        print("CẢNH BÁO: MONICA_API_KEY chưa được cấu hình. Bỏ qua test này.")
        return None
    prompt = "Dịch 'Good morning, how are you?' sang tiếng Pháp."
    # Sử dụng model mặc định từ settings, nhưng tùy chỉnh các tham số khác
    # Điều này an toàn hơn là hardcode một model có thể không được hỗ trợ
    custom_model = settings.DEFAULT_MONICA_MODEL
    test_runner_logger.info(f"Sử dụng model '{custom_model}' cho test_successful_call_custom_params.")
    response = ask_monica(prompt, model=custom_model, temperature=0.5, stream=False, timeout=45)
    assert response is not None, "Phản hồi không nên là None cho một cuộc gọi thành công với tham số tùy chỉnh."
    assert len(response) > 0, "Phản hồi không nên rỗng."
    return response

def test_missing_api_key():
    """Test 3: Xử lý trường hợp MONICA_API_KEY bị thiếu."""
    original_key = settings.MONICA_API_KEY
    settings.MONICA_API_KEY = None # Tạm thời xóa API key
    test_runner_logger.info("Đã tạm thời đặt MONICA_API_KEY thành None cho test_missing_api_key.")
    try:
        prompt = "Prompt này sẽ không được gửi đi do thiếu key."
        response = ask_monica(prompt)
        assert response is None, "Hàm ask_monica nên trả về None khi API key bị thiếu."
        test_runner_logger.info("test_missing_api_key: ask_monica đã trả về None như mong đợi.")
    finally:
        settings.MONICA_API_KEY = original_key # Khôi phục API key
        test_runner_logger.info("Đã khôi phục MONICA_API_KEY ban đầu sau test_missing_api_key.")
    return None # Test này không mong đợi giá trị trả về cụ thể ngoài None

def test_invalid_api_key():
    """Test 4: Xử lý trường hợp MONICA_API_KEY không hợp lệ."""
    original_key = settings.MONICA_API_KEY
    invalid_test_key = "sk-INVALID_KEY_FOR_SURE_1234567890ABCDEF"
    settings.MONICA_API_KEY = invalid_test_key
    test_runner_logger.info(f"Đã tạm thời đặt MONICA_API_KEY thành key không hợp lệ: '{invalid_test_key}' cho test_invalid_api_key.")
    try:
        prompt = "Prompt này sẽ gây lỗi HTTP 401 do key không hợp lệ."
        response = ask_monica(prompt)
        assert response is None, "Hàm ask_monica nên trả về None khi API key không hợp lệ (lỗi HTTP)."
        test_runner_logger.info("test_invalid_api_key: ask_monica đã trả về None như mong đợi.")
    finally:
        settings.MONICA_API_KEY = original_key
        test_runner_logger.info("Đã khôi phục MONICA_API_KEY ban đầu sau test_invalid_api_key.")
    return None

def test_network_timeout():
    """Test 5: Xử lý trường hợp timeout khi gọi API."""
    if not settings.MONICA_API_KEY: # Cần key hợp lệ để thực sự gọi API và gây timeout
        test_runner_logger.warning("Bỏ qua 'test_network_timeout' do MONICA_API_KEY chưa được cấu hình.")
        print("CẢNH BÁO: MONICA_API_KEY chưa được cấu hình. Bỏ qua test timeout.")
        return None
    prompt = "Prompt này sẽ bị timeout do thời gian chờ quá ngắn."
    response = ask_monica(prompt, timeout=0.001) # Timeout cực ngắn (1ms)
    assert response is None, "Hàm ask_monica nên trả về None khi bị timeout."
    test_runner_logger.info("test_network_timeout: ask_monica đã trả về None như mong đợi.")
    return None

def test_invalid_endpoint():
    """Test 6: Xử lý trường hợp endpoint không hợp lệ."""
    original_endpoint = settings.MONICA_API_ENDPOINT
    invalid_test_endpoint = "http://một-url-chắc-chắn-không-tồn-tại-12345.local/api"
    settings.MONICA_API_ENDPOINT = invalid_test_endpoint
    test_runner_logger.info(f"Đã tạm thời đặt MONICA_API_ENDPOINT thành: '{invalid_test_endpoint}' cho test_invalid_endpoint.")
    
    original_key_for_this_test = settings.MONICA_API_KEY
    if not settings.MONICA_API_KEY: # Cần có key để không bị return None sớm
        settings.MONICA_API_KEY = "TEMP_KEY_VALUE_FOR_ENDPOINT_TEST"
        test_runner_logger.info("Sử dụng API key tạm thời cho test_invalid_endpoint vì key gốc là None.")

    try:
        prompt = "Prompt này sẽ gây lỗi kết nối do endpoint sai."
        response = ask_monica(prompt)
        assert response is None, "Hàm ask_monica nên trả về None khi endpoint không hợp lệ."
        test_runner_logger.info("test_invalid_endpoint: ask_monica đã trả về None như mong đợi.")
    finally:
        settings.MONICA_API_ENDPOINT = original_endpoint # Khôi phục endpoint
        settings.MONICA_API_KEY = original_key_for_this_test # Khôi phục key
        test_runner_logger.info("Đã khôi phục MONICA_API_ENDPOINT và MONICA_API_KEY (nếu tạm đổi) ban đầu sau test_invalid_endpoint.")
    return None

# --- Chạy các test ---
if __name__ == "__main__":
    test_runner_logger.info("===== BẮT ĐẦU BỘ THỬ NGHIỆM CHO ASK_MONICA.PY =====")
    print("\n===== CHẠY THỬ NGHIỆM CHO ASK_MONICA.PY =====\n")

    # Kiểm tra MONICA_API_KEY trước khi chạy các test cần key
    if not settings.MONICA_API_KEY:
        warning_message = "MONICA_API_KEY CHƯA ĐƯỢC CẤU HÌNH TRONG .ENV HOẶC SETTINGS.PY"
        test_runner_logger.warning(warning_message)
        print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"!!! CẢNH BÁO: {warning_message} !!!")
        print("!!! Một số test (như gọi API thành công, timeout) sẽ bị bỏ qua hoặc     !!!")
        print("!!! có thể không hoạt động đúng như mong đợi.                            !!!")
        print("!!! Vui lòng cấu hình MONICA_API_KEY trong file .env của bạn.             !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")

    # Chạy tuần tự các test
    run_test("Gọi API thành công (tham số mặc định)", test_successful_call_default_params)
    run_test("Gọi API thành công (tham số tùy chỉnh)", test_successful_call_custom_params)
    run_test("Xử lý API Key bị thiếu", test_missing_api_key)
    run_test("Xử lý API Key không hợp lệ (HTTP Error)", test_invalid_api_key)
    run_test("Xử lý Timeout khi gọi API", test_network_timeout)
    run_test("Xử lý Endpoint không hợp lệ", test_invalid_endpoint)

    test_runner_logger.info("===== HOÀN THÀNH BỘ THỬ NGHIỆM CHO ASK_MONICA.PY =====")
    print("\n===== KẾT THÚC THỬ NGHIỆM =====\n")