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
    log_file="output/monica_log.txt"
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

    reply = None
    try:
        response = requests.post(ENDPOINT, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        reply = result["choices"][0]["message"]["content"].strip()
    except requests.exceptions.HTTPError as http_err:
        print(f"\n🔴 Lỗi HTTP: {http_err}")
        print(response.text)
    except requests.exceptions.RequestException as err:
        print(f"\n🔴 Lỗi gửi yêu cầu: {err}")
    except Exception as e:
        print(f"\n🔴 Lỗi không xác định: {e}")
        reply = None

    # --- Ghi log ra file ---
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n" + "="*60 + "\n")
            f.write("PROMPT:\n" + prompt + "\n")
            f.write("-"*40 + "\n")
            f.write("RESPONSE:\n" + (reply or "[NO RESPONSE]") + "\n")
    except Exception as log_err:
        print(f"⚠️ Không thể ghi log Monica: {log_err}")

    return reply

