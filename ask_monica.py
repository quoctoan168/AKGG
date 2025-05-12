import requests
import json
from prompt_builder import Prompt

def read_API_key(file_path, model_name):
    """Đọc API key từ file theo tên model."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.strip().startswith(f"{model_name}:"):
                    return line.split(":", 1)[1].strip()
        print(f"❌ Không tìm thấy API key cho model '{model_name}' trong file.")
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file '{file_path}'.")
    except Exception as e:
        print(f"❌ Lỗi khi đọc API key: {e}")
    return None


def ask_monica(prompt, model="gpt-4o", key_file="API_Key.txt"):
    """Gửi prompt tới Monica và trả về phản hồi dưới dạng chuỗi."""
    API_KEY = read_API_key(key_file, "monica")
    ENDPOINT = "https://openapi.monica.im/v1/chat/completions"

    if not API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "temperature": 0.7,
        "stream": False
    }

    try:
        response = requests.post(ENDPOINT, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

        # Trả về nội dung trả lời
        return result["choices"][0]["message"]["content"].strip()

    except requests.exceptions.HTTPError as http_err:
        print(f"\n🔴 Lỗi HTTP: {http_err}")
        print(response.text)
    except requests.exceptions.RequestException as err:
        print(f"\n🔴 Lỗi gửi yêu cầu: {err}")
    except Exception as e:
        print(f"\n🔴 Lỗi không xác định: {e}")
    
    return None

# Khởi tạo prompt
my_prompt = Prompt(
    task_description="Sinh ontology từ mô tả nghiệp vụ.",
    context="Mô hình phục vụ hệ thống quản lý đào tạo tại đại học.",
    input_data="Các thực thể gồm Sinh viên, Môn học, Giảng viên, Lịch học.",
    goal="Xác định class, thuộc tính, mối quan hệ và ràng buộc cơ bản.",
    output_format="Dưới dạng OWL cơ bản, hoặc dạng bảng đơn giản phân loại rõ.",
    constraints="Chỉ mô hình hóa kiến thức cốt lõi, tránh dư thừa.",
    instructions="Trình bày súc tích, rõ ràng, chia mục hợp lý."
)

# Sinh nội dung từ class
full_prompt = my_prompt.build()

reply = ask_monica(full_prompt)
if reply:
    print("\n🟢 Phản hồi từ Monica:")
    print(reply)