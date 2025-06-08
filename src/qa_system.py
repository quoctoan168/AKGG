# File: src/qa_system.py (Kiến trúc "Tư duy theo chuỗi")

import logging
import json
import re
import os
from typing import List, Dict, Any, Optional

try:
    from config import settings
    from src.neo4j_handler import Neo4jHandler
    from src.ask_monica import ask_monica
    from src.prompt_builder import Prompt
    from src.owl_handler import load_ontology
    from src import vn_embedding_search as embedding
    EMBEDDING_ENABLED = True
except ImportError as e:
    print(f"Lỗi import trong qa_system.py: {e}. Một số chức năng có thể không hoạt động.")
    settings, Neo4jHandler, ask_monica, Prompt, load_ontology, embedding = (None,)*6
    EMBEDDING_ENABLED = False

logger = logging.getLogger(__name__)

class QASystem:
    def __init__(self):
        logger.info("Đang khởi tạo Hệ thống Hỏi-Đáp (QA System)...")
        self.neo4j_handler = Neo4jHandler()
        if not self.neo4j_handler.driver:
            raise ConnectionError("Không thể kết nối tới Neo4j.")
        
        self.graph_schema = self._load_graph_schema()
        if not self.graph_schema:
            raise RuntimeError("Không thể tải lược đồ ontology.")
        
        if EMBEDDING_ENABLED:
            self._initialize_semantic_search()
        
        logger.info("✅ Hệ thống Hỏi-Đáp đã sẵn sàng.")

    def _initialize_semantic_search(self):
        logger.info("Đang khởi tạo chỉ mục tìm kiếm ngữ nghĩa (FAISS)...")
        index_path = getattr(settings, 'FAISS_INDEX_PATH', 'faiss_index.index')
        if os.path.exists(index_path):
            logger.info("Phát hiện chỉ mục đã tồn tại. Bỏ qua bước xây dựng lại.")
            return
        logger.info("Bắt đầu xây dựng chỉ mục mới từ dữ liệu trong Neo4j...")
        entities_map = self.neo4j_handler.get_all_entities_with_aliases()
        if not entities_map:
            logger.warning("Không có thực thể nào trong KG để xây dựng chỉ mục.")
            return
        all_names = list(entities_map.keys())
        logger.info(f"Đang xây dựng chỉ mục cho {len(all_names)} thực thể và bí danh...")
        embedding.build_index(all_names, save=True)
        logger.info("✅ Xây dựng chỉ mục tìm kiếm ngữ nghĩa thành công.")

    def _load_graph_schema(self) -> Optional[Dict[str, List[str]]]:
        ontology_path = os.path.join(settings.OUTPUT_DIR, settings.DEFAULT_OWL_FILENAME)
        try:
            onto = load_ontology(ontology_path)
            if not onto: return None
            schema = {
                "node_labels": sorted(list(set(cls.name for cls in onto.classes()))),
                "rel_types": sorted(list(set(prop.name for prop in onto.object_properties())))
            }
            logger.info("Tải lược đồ đồ thị thành công.")
            return schema
        except Exception as e:
            logger.error(f"Lỗi khi tải lược đồ đồ thị: {e}", exc_info=True)
            return None

    def _call_ai_for_json(self, prompt: str) -> Optional[Dict]:
        """Hàm gọi AI và đảm bảo parse được JSON trả về."""
        ai_response = ask_monica(prompt=prompt)
        if not ai_response: return None
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
            json_str = json_match.group(1) if json_match else re.search(r'\{.*\}', ai_response, re.DOTALL).group(0)
            return json.loads(json_str.strip())
        except (AttributeError, json.JSONDecodeError):
            logger.error(f"Lỗi phân tích JSON từ AI. Phản hồi:\n{ai_response}")
            return None

    def _step1_extract_and_expand_entities(self, question: str) -> Optional[Dict[str, List[str]]]:
        """Trích xuất và mở rộng thực thể từ câu hỏi."""
        logger.info(f"Bước 1: Trích xuất và Mở rộng thực thể cho: '{question}'")
        
        prompt = Prompt(
            task_description="Trích xuất các danh từ riêng hoặc cụm danh từ chính (key entities) từ câu hỏi.",
            input_data=f"Câu hỏi: \"{question}\"",
            output_format='```json\n{"entities": ["thực thể 1", "thực thể 2"]}\n```'
        ).build()
        
        response = self._call_ai_for_json(prompt)
        if not (response and response.get("entities")):
            logger.warning("Không trích xuất được thực thể thô nào.")
            return None

        raw_entities = response["entities"]
        logger.info(f"Thực thể thô được trích xuất: {raw_entities}")

        if not EMBEDDING_ENABLED: return {entity: [entity] for entity in raw_entities}

        expanded_entities = {}
        for entity in raw_entities:
            try:
                similar_names = embedding.search_phrase(entity, top_k=3)
                if similar_names:
                    logger.info(f"Thực thể '{entity}' được mở rộng thành: {similar_names}")
                    expanded_entities[entity] = similar_names
            except Exception as e:
                logger.error(f"Lỗi tìm kiếm ngữ nghĩa cho '{entity}': {e}")
        
        return expanded_entities

    def _step2_generate_subgraph_query(self, question: str, expanded_entities: Optional[Dict[str, List[str]]]) -> Optional[str]:
        """Tạo truy vấn Cypher để lấy về một cụm thông tin liên quan."""
        logger.info("Bước 2: Tạo truy vấn Cypher để lấy cụm thông tin (subgraph)...")

        context_parts = [
            "Lược đồ đồ thị:",
            f"- Nhãn Node: :Instance",
            f"- Thuộc tính phân loại: class_label (VD: {self.graph_schema['node_labels'][:5]}...)",
            f"- Các loại quan hệ: {self.graph_schema['rel_types'][:5]}...",
            "\nGợi ý: Đồ thị là Event-Centric. Hãy ưu tiên các truy vấn đi qua nút Sự kiện."
        ]
        if expanded_entities:
            context_parts.append(f"\nThông tin ngữ nghĩa đã xác định (thực thể trong câu hỏi -> thực thể trong KG):\n{json.dumps(expanded_entities, ensure_ascii=False, indent=2)}")
        
        prompt = Prompt(
            task_description="Viết một câu lệnh Cypher để lấy một cụm thông tin (subgraph) liên quan đến câu hỏi. Truy vấn nên trả về các đường đi (path) hoặc bảng thông tin.",
            context="\n".join(context_parts),
            input_data=f"Câu hỏi của người dùng: \"{question}\"",
            goal="Tạo một truy vấn Cypher phức hợp để lấy tất cả các nút và cạnh trong bán kính 1 hoặc 2 bước nhảy từ các thực thể đã biết. Ưu tiên trả về dưới dạng các đường đi `p=()-[*1..2]-()`. Nếu không, trả về bảng các thành phần `a.name, type(r), b.name`.",
            output_format='```json\n{"cypher_query": "MATCH p=(n)-[*1..2]-(m) WHERE n.name IN [...] RETURN p LIMIT 10"}\n```'
        ).build()

        response_data = self._call_ai_for_json(prompt)
        if response_data and "cypher_query" in response_data:
            cypher_query = response_data.get("cypher_query")
            logger.info(f"Đã tạo truy vấn Subgraph: {cypher_query}")
            return cypher_query
        
        logger.error("Tạo truy vấn Subgraph thất bại.")
        return None

    def _step3_synthesize_answer_from_subgraph(self, question: str, subgraph_data: List[Any]) -> str:
        """Tổng hợp câu trả lời tự nhiên từ cụm thông tin đã lấy về."""
        if not subgraph_data:
            return "Tôi không tìm thấy thông tin nào trong cơ sở tri thức để trả lời câu hỏi này."
        
        logger.info("Bước 3: Tổng hợp câu trả lời từ cụm thông tin...")
        
        prompt = Prompt(
            task_description="Bạn là một trợ lý ảo thông thái. Dựa vào câu hỏi gốc của người dùng và một cụm thông tin (subgraph) được cung cấp từ Knowledge Graph, hãy tạo ra một câu trả lời tự nhiên, đầy đủ và thân thiện bằng tiếng Việt.",
            context=f"Câu hỏi gốc của người dùng là: \"{question}\"",
            input_data=f"Dữ liệu subgraph từ Knowledge Graph:\n{json.dumps(subgraph_data, default=str, ensure_ascii=False, indent=2)}",
            goal="Tạo một câu trả lời duy nhất, súc tích, đi thẳng vào vấn đề, chỉ dựa vào thông tin được cung cấp.",
            output_format="Một câu hoặc một đoạn văn ngắn bằng tiếng Việt."
        ).build()
        
        response = ask_monica(prompt)
        return response if response else "Đã tìm thấy dữ liệu nhưng có lỗi khi diễn giải câu trả lời."

    def answer(self, question: str) -> str:
        """
        Hàm chính để trả lời câu hỏi theo kiến trúc "Tư duy theo chuỗi".
        """
        # Bước 1: Trích xuất và mở rộng thực thể
        expanded_entities = self._step1_extract_and_expand_entities(question)
        
        # Bước 2: Tạo và thực thi truy vấn lấy subgraph
        cypher_query = self._step2_generate_subgraph_query(question, expanded_entities)
        if not cypher_query:
            return "Xin lỗi, tôi không thể tạo được truy vấn cho cơ sở tri thức từ câu hỏi của bạn."
        
        records = self.neo4j_handler._execute_query(cypher_query)
        
        # Bước 3: Tổng hợp câu trả lời từ kết quả
        final_answer = self._step3_synthesize_answer_from_subgraph(question, [r.data() for r in records])
        
        return final_answer