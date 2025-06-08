# File: run_qa.py
import os
import sys

# Thiết lập sys.path để import các module từ src/ và config/
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

try:
    from src.qa_system import QASystem
except ImportError:
    print("FATAL: Không thể import QASystem. Hãy chắc chắn bạn đang chạy file này từ thư mục gốc của dự án.")
    sys.exit(1)
except Exception as e:
    print(f"Lỗi không xác định khi khởi tạo: {e}")
    sys.exit(1)

def main():
    """
    Hàm chính để chạy giao diện hỏi-đáp trên terminal.
    """
    print("==============================================")
    print("  HỆ THỐNG HỎI - ĐÁP KNOWLEDGE GRAPH LỊCH SỬ")
    print("==============================================")
    print("Gõ câu hỏi của bạn và nhấn Enter.")
    print("Gõ 'thoat', 'exit', hoặc 'quit' để kết thúc.")
    print("----------------------------------------------")

    try:
        qa_system = QASystem()
    except Exception as e:
        print(f"\nFATAL: Không thể khởi tạo QA System: {e}")
        print("Vui lòng kiểm tra lại kết nối Neo4j và file ontology 'generated_ontology.owl' đã tồn tại trong thư mục output.")
        return

    while True:
        try:
            question = input("\nBạn hỏi: ")
            if question.lower() in ['thoat', 'exit', 'quit']:
                print("Cảm ơn bạn đã sử dụng. Tạm biệt!")
                break
            
            if not question.strip():
                continue

            print("Đang xử lý, vui lòng chờ...")
            answer = qa_system.answer(question)
            
            print("\n-----------------")
            print(f"Câu trả lời: {answer}")
            print("-----------------")

        except KeyboardInterrupt:
            print("\nCảm ơn bạn đã sử dụng. Tạm biệt!")
            break
        except Exception as e:
            print(f"\nĐã xảy ra lỗi không mong muốn: {e}")

if __name__ == "__main__":
    main()