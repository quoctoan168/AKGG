# File: main.py
# Version: Cấu hình chế độ chạy tự động (CREATE_NEW/APPEND)

import os
import logging
import sys
import shutil
import logging.handlers

# --- Bước 1: Thiết lập sys.path ĐẦU TIÊN ---
# Đảm bảo các module trong thư mục gốc (SOURCE) có thể được import
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

# --- Bước 2: Import các module cần thiết ---
# Import settings trước tiên để các module khác có thể sử dụng
try:
    from config import settings
except (ImportError, EnvironmentError) as e:
    print(f"FATAL: Lỗi nghiêm trọng khi import hoặc kiểm tra settings. Lỗi: {e}")
    sys.exit(1)

# Import các module của dự án
try:
    from src.context_builder import ContextBuilder
    from src.neo4j_handler import Neo4jHandler
    from src.knowledge_graph_builder import KnowledgeGraphBuilder
    from src.ask_monica import _setup_loggers_if_not_configured as setup_ask_monica_loggers
    import src.cq_parser as cq_parser
    import src.owl_handler as owl_handler
except ImportError as e:
    print(f"FATAL: Không thể import các module dự án. Hãy chắc chắn các file __init__.py tồn tại. Lỗi: {e}")
    sys.exit(1)

# --- Bước 3: Thiết lập Logger cho main.py ---
main_logger = logging.getLogger("MainPipeline")
main_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Handler cho việc in log ra console
main_ch = logging.StreamHandler(sys.stdout)
main_ch.setFormatter(formatter)
main_logger.addHandler(main_ch)
main_logger.propagate = False # Ngăn log bị lặp lại bởi root logger

# Handler cho việc ghi log ra file (sẽ được thiết lập trong hàm)
main_log_file_path = os.path.join(settings.OUTPUT_DIR, "main_pipeline.log")
main_fh = None

def setup_main_file_logger(mode='a'):
    """Thiết lập hoặc thiết lập lại file handler cho main logger."""
    global main_fh
    if main_fh:
        main_logger.removeHandler(main_fh)
        main_fh.close()
    try:
        # settings.py đã đảm bảo thư mục này tồn tại
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        main_fh = logging.FileHandler(main_log_file_path, encoding='utf-8', mode=mode)
        main_fh.setFormatter(formatter)
        main_logger.addHandler(main_fh)
        main_logger.info(f"File logger cho MainPipeline được thiết lập/mở lại (mode: {mode}).")
    except Exception as e:
        main_logger.error(f"Không thể tạo/mở lại file logger cho MainPipeline tại {main_log_file_path}: {e}.")

# --- HÀM TIỆN ÍCH ---
def close_all_file_handlers():
    """Tìm, đóng và gỡ bỏ tất cả các FileHandler đang mở để cho phép xóa file."""
    loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
    loggers.append(logging.getLogger()) # Bao gồm cả root logger

    main_logger.info("Bắt đầu đóng và gỡ bỏ tất cả các file logging handlers...")
    for logger in loggers:
        for handler in logger.handlers[:]: # Lặp trên một bản sao
            if isinstance(handler, logging.FileHandler):
                try:
                    handler_path = getattr(handler, 'baseFilename', 'Không xác định')
                    main_logger.debug(f"Đang đóng handler cho file: {handler_path} của logger '{logger.name}'")
                    handler.close()
                    logger.removeHandler(handler)
                except Exception as e:
                    main_logger.warning(f"Lỗi khi đóng handler cho file {getattr(handler, 'baseFilename', 'N/A')}: {e}")
    main_logger.info("Hoàn tất việc đóng và gỡ bỏ các file logging handlers.")

def reset_project_state(output_dir: str, neo4j_handler: Neo4jHandler) -> bool:
    """Xóa nội dung thư mục output và dữ liệu trong Neo4j."""
    main_logger.info("Bắt đầu quá trình reset trạng thái dự án...")
    all_successful = True

    # Xóa thư mục output
    main_logger.info(f"Đang xóa nội dung trong thư mục output: {output_dir}")
    if os.path.isdir(output_dir):
        # Giữ lại các thư mục rỗng, chỉ xóa file
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            try:
                if os.path.isfile(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path): # Xóa thư mục con và nội dung của nó
                    shutil.rmtree(item_path)
            except Exception as e:
                main_logger.error(f"Lỗi khi xóa '{item_path}': {e}", exc_info=True)
                all_successful = False
    
    # Xóa dữ liệu Neo4j
    main_logger.info("Đang xóa toàn bộ dữ liệu trong Neo4j...")
    if not neo4j_handler.clear_database():
        main_logger.error("Lệnh xóa dữ liệu Neo4j thất bại.")
        all_successful = False

    if all_successful:
        main_logger.info("✅ Quá trình reset trạng thái dự án hoàn tất thành công.")
    else:
        main_logger.error("❌ Quá trình reset trạng thái dự án có lỗi.")
    return all_successful

# --- HÀM CHÍNH: RUN_PIPELINE ---
def run_pipeline():
    """Thực thi toàn bộ pipeline của dự án."""
    # Bước 0: Kiểm tra cấu hình và khởi tạo kết nối
    try:
        settings.check_critical_settings()
        main_logger.info("Các cấu hình quan trọng đã được xác minh.")
        neo4j_handler = Neo4jHandler()
        if not neo4j_handler.driver:
            main_logger.critical("Không thể khởi tạo Neo4j driver. Dừng pipeline.")
            return
        main_logger.info("✅ Neo4jHandler đã được khởi tạo thành công.")
    except Exception as e:
        main_logger.critical(f"Lỗi nghiêm trọng khi khởi tạo: {e}", exc_info=True)
        return

    # --- Đọc chế độ chạy từ settings và thực hiện reset nếu cần ---
    if settings.PIPELINE_MODE == 'CREATE_NEW':
        main_logger.info("Chế độ 'Tạo mới' được kích hoạt. Đang reset trạng thái dự án...")
        close_all_file_handlers() # Đóng file log trước khi xóa
        if reset_project_state(settings.OUTPUT_DIR, neo4j_handler):
            # Thiết lập lại logger để ghi vào file mới
            setup_main_file_logger(mode='w')
            setup_ask_monica_loggers()
            main_logger.info("✅ Trạng thái dự án đã được reset.")
        else:
            main_logger.error("Reset dự án thất bại. Dừng pipeline để tránh các lỗi không mong muốn.")
            if neo4j_handler: neo4j_handler.close()
            return
    elif settings.PIPELINE_MODE == 'APPEND':
        # Với chế độ APPEND, chúng ta sẽ ghi tiếp vào file log cũ (nếu có)
        setup_main_file_logger(mode='a')
        main_logger.info("Chế độ 'Bổ sung' được kích hoạt. Bỏ qua bước reset.")
    else:
        setup_main_file_logger(mode='a')
        main_logger.error(f"Chế độ pipeline '{settings.PIPELINE_MODE}' không hợp lệ. Chỉ chấp nhận 'CREATE_NEW' hoặc 'APPEND'. Dừng chương trình.")
        if neo4j_handler: neo4j_handler.close()
        return

    main_logger.info("🚀 BẮT ĐẦU PIPELINE XÂY DỰNG TRI THỨC 🚀")
    
    # Các bước pipeline còn lại...
    # --- Bước 1: Xây dựng Project Context ---
    main_logger.info("--- Bước 1: Xây dựng Project Context ---")
    project_context_summary = "Không có context"
    context_builder = ContextBuilder(
        project_description="Một hệ thống phân tích văn bản lịch sử, trích xuất thông tin khóa và xây dựng đồ thị tri thức.",
        project_goal="Tạo ra một đồ thị tri thức và ontology có thể truy vấn được từ các tài liệu văn bản được cung cấp."
    )
    context_builder.run_pipeline(
        cq_questions_path=os.path.join(settings.CQ_DIR, "CQ_questions.txt"),
    )
    if context_builder.project_context_summary:
        project_context_summary = context_builder.project_context_summary
        main_logger.info("✅ Project context đã được xây dựng và tải.")
    else:
        main_logger.warning("Không tạo được project context. Các bước sau có thể bị ảnh hưởng.")

    # --- Bước 2: Xây dựng Ontology từ CQ Answers ---
    main_logger.info("--- Bước 2: Xây dựng Ontology từ CQ Answers ---")
    cq_answers_path = os.path.join(settings.OUTPUT_DIR, settings.CQ_ANSWERS_FILENAME)
    seed_ontology_path = os.path.join(settings.DATA_DIR, 'seed_ontology.owl')
    project_ontology_path = os.path.join(settings.OWL_OUTPUT_DIR, settings.DEFAULT_OWL_FILENAME)

    if os.path.exists(cq_answers_path) and os.path.exists(seed_ontology_path):
        main_logger.info(f"Phân tích các định nghĩa từ '{cq_answers_path}'...")
        class_defs, prop_defs, rel_defs = cq_parser.parse_cq_answers_for_ontology(cq_answers_path)

        if class_defs or prop_defs or rel_defs:
            main_logger.info(f"Tải ontology hạt giống từ '{seed_ontology_path}'...")
            seed_onto = owl_handler.load_ontology(seed_ontology_path)
            if seed_onto:
                main_logger.info("Cập nhật ontology hạt giống với các định nghĩa mới...")
                if owl_handler.update_ontology_with_definitions(
                    onto=seed_onto, class_definitions=class_defs, prop_definitions=prop_defs,
                    rel_definitions=rel_defs, save_path=project_ontology_path
                ):
                    main_logger.info(f"✅ Ontology dự án đã được xây dựng và lưu tại: {project_ontology_path}")
                else:
                    main_logger.error("Lỗi khi cập nhật hoặc lưu ontology dự án.")
            else:
                main_logger.error(f"Không thể tải ontology hạt giống từ '{seed_ontology_path}'.")
        else:
            main_logger.warning("Không phân tích được định nghĩa nào từ file CQ answers.")
    else:
        main_logger.warning(f"Không tìm thấy file '{cq_answers_path}' hoặc '{seed_ontology_path}'. Bỏ qua bước xây dựng ontology.")
    
    # --- Bước 3: Khởi tạo và Xây dựng Knowledge Graph ---
    main_logger.info("--- Bước 3: Khởi tạo và Xây dựng Knowledge Graph ---")
    kg_builder = KnowledgeGraphBuilder(
        neo4j_handler=neo4j_handler,
        project_context=project_context_summary
    )
    
    if not os.path.isdir(settings.INPUT_TEXT_DIR):
        main_logger.warning(f"Thư mục đầu vào '{settings.INPUT_TEXT_DIR}' không tìm thấy.")
    else:
        main_logger.info(f"Bắt đầu xử lý các file đầu vào từ '{settings.INPUT_TEXT_DIR}'...")
        for filename in sorted(os.listdir(settings.INPUT_TEXT_DIR)):
            if filename.lower().endswith(".txt"):
                file_path = os.path.join(settings.INPUT_TEXT_DIR, filename)
                main_logger.info(f"--- Đang xử lý file: {filename} ---")
                
                extracted_info = context_builder.extract_information_from_file(file_path)
                
                if not extracted_info:
                    main_logger.warning(f"Không có thông tin nào được trích xuất từ '{filename}'. Bỏ qua.")
                    continue
                main_logger.info(f"Đã trích xuất {len(extracted_info)} mẩu thông tin từ '{filename}'.")

                try:
                    kg_builder.process_extracted_info_to_graph(
                        extracted_info_list=extracted_info,
                        ontology_path=project_ontology_path,
                        source_identifier=filename
                    )
                except Exception as e:
                     main_logger.error(f"Lỗi nghiêm trọng khi xây dựng KG cho file '{filename}': {e}", exc_info=True)

    main_logger.info("--- Bước 4: Dọn dẹp ---")
    if neo4j_handler:
        neo4j_handler.close()
    main_logger.info("🏁 PIPELINE ĐÃ HOÀN TẤT. 🏁")

# --- Điểm vào của chương trình ---
if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        main_logger.critical(f"LỖI KHÔNG XÁC ĐỊNH TRONG PIPELINE: {e}", exc_info=True)
    finally:
        main_logger.info("Đảm bảo tất cả các file log đã được đóng khi kết thúc.")
        close_all_file_handlers()
        logging.shutdown()