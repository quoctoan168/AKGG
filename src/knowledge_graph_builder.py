# File: src/knowledge_graph_builder.py (Sửa lỗi 'ontology_path is not defined')
import logging
import json
import re
import os
import itertools
from typing import List, Dict, Any, Optional, Tuple
from unicodedata import normalize, combining

from .ask_monica import ask_monica
from .neo4j_handler import Neo4jHandler
from .prompt_builder import Prompt
from .owl_handler import load_ontology, update_ontology_with_definitions, save_ontology

logger = logging.getLogger(__name__)

class KnowledgeGraphBuilder:
    def __init__(self, neo4j_handler: Neo4jHandler, project_context: Optional[str] = None):
        if not neo4j_handler or not neo4j_handler.driver:
            raise ValueError("Neo4jHandler không hợp lệ hoặc chưa kết nối.")
        self.neo4j_handler = neo4j_handler
        self.project_context = project_context if project_context else "Không có bối cảnh dự án cụ thể."
        
        self.resolution_cache_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'output', 'resolution_cache.json')
        self.resolution_cache = self._load_cache()

        logger.info("KnowledgeGraphBuilder (Event-Centric with Entity Resolution & Event Linking) initialized.")

    def _load_cache(self) -> Dict[str, str]:
        if os.path.exists(self.resolution_cache_path):
            try:
                with open(self.resolution_cache_path, 'r', encoding='utf-8') as f:
                    logger.info(f"Đã tải cache đồng nhất thực thể từ: {self.resolution_cache_path}")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Lỗi khi tải cache từ {self.resolution_cache_path}: {e}. Bắt đầu với cache rỗng.")
        return {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.resolution_cache_path), exist_ok=True)
            with open(self.resolution_cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.resolution_cache, f, ensure_ascii=False, indent=4)
            logger.info(f"Cache đồng nhất thực thể đã được lưu vào: {self.resolution_cache_path}")
        except IOError as e:
            logger.error(f"Lỗi khi lưu cache: {e}")

    def _normalize_string(self, text: str) -> str:
        if not text: return ""
        text = text.lower().strip()
        text = ''.join(c for c in normalize('NFD', text) if combining(c) == 0)
        return text

    def _get_schema_from_ontology(self, onto: Any) -> Dict[str, Any]:
        schema = {"classes": [], "relations": []}
        if not onto: return schema
        for cls in onto.classes():
            schema["classes"].append({"id": cls.name, "label": getattr(cls.label, "first", lambda: cls.name)()})
        for prop in onto.object_properties():
            domain_names = [d.name for d in prop.domain]
            range_names = [r.name for r in prop.range]
            schema["relations"].append({"id": prop.name, "label": getattr(prop.label, "first", lambda: prop.name)(), "domain": domain_names, "range": range_names})
        return schema

    def _call_ai_with_json_parsing(self, prompt: str) -> Optional[Dict]:
        ai_response = ask_monica(prompt=prompt)
        if not ai_response: return None
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
            json_str = json_match.group(1) if json_match else re.search(r'\{.*\}', ai_response, re.DOTALL).group(0)
            return json.loads(json_str)
        except (AttributeError, json.JSONDecodeError) as e:
            logger.error(f"Lỗi khi phân tích JSON từ AI: {e}", exc_info=False)
            logger.debug(f"Phản hồi AI không hợp lệ:\n{ai_response}")
            return None

    def _model_fact_as_event(self, fact: str, onto: Any) -> Optional[Dict]:
        logger.debug(f"  -> Mô hình hóa sự kiện cho fact: '{fact[:80]}...'")
        schema = self._get_schema_from_ontology(onto)
        prompt = Prompt(
            task_description="Nhiệm vụ của bạn là phân tích một câu thông tin duy nhất và mô hình hóa nó theo phương pháp 'Event-Centric'. Xác định hành động chính (sự kiện) và các thực thể liên quan (ai/cái gì, ở đâu, khi nào).",
            context=f"Lược đồ Ontology hiện tại để tham khảo:\nClasses: {json.dumps(schema['classes'], ensure_ascii=False)}\nRelations: {json.dumps(schema['relations'], ensure_ascii=False)}",
            input_data=f"Câu thông tin cần mô hình hóa:\n```text\n{fact}\n```",
            goal="Tạo một cấu trúc JSON mô tả sự kiện này. Sự kiện là nút trung tâm, các thực thể khác kết nối vào nó.",
            output_format="""Chỉ trả về một đối tượng JSON duy nhất.
```json
{
  "event": {"name": "Tên_gợi_nhớ_cho_sự_kiện", "class_id": "ClassID_cho_sự_kiện"},
  "participants": [{"name": "Tên thực thể", "class_id": "ClassID_Thực_thể", "relation_to_event": "RelationID"}]
}
```""",
            constraints="Tất cả `class_id` và `relation_to_event` phải là ID từ ontology nếu có, hoặc tạo ID mới dạng PascalCase nếu cần. `participants` chứa tất cả các đối tượng, tác nhân, địa điểm, thời gian liên quan."
        ).build()
        return self._call_ai_with_json_parsing(prompt)

    def _resolve_entities_in_batch(self, new_entities: Dict[str, Any], existing_alias_map: Dict[str, str]) -> Dict[str, str]:
        resolution_map, batch_to_verify = {}, []
        normalized_existing_map = {self._normalize_string(alias): canonical for alias, canonical in existing_alias_map.items()}
        logger.info(f"Bắt đầu đồng nhất cho {len(new_entities)} thực thể mới...")
        for name, data in new_entities.items():
            if name in self.resolution_cache:
                resolution_map[name] = self.resolution_cache[name]
                continue
            normalized_name = self._normalize_string(name)
            if normalized_name in normalized_existing_map:
                resolution_map[name] = normalized_existing_map[normalized_name]
                self.resolution_cache[name] = resolution_map[name]
                continue
            batch_to_verify.append({"new_name": name, "class_id": data["class_id"]})
        logger.info(f"{len(resolution_map)} thực thể được đồng nhất tự động/từ cache.")
        if not batch_to_verify: return resolution_map
        
        logger.info(f"Gửi {len(batch_to_verify)} thực thể cần xác thực đến AI...")
        prompt = Prompt(
            task_description="Với mỗi 'thực thể mới', xác định xem nó có trùng với một 'thực thể đã có' hay không. Nếu không, nó là thực thể mới.",
            context=f"Danh sách thực thể đã có (tên chính tắc): {json.dumps(list(set(existing_alias_map.values())), ensure_ascii=False)}",
            input_data=f"Danh sách thực thể mới cần đồng nhất:\n{json.dumps(batch_to_verify, ensure_ascii=False)}",
            goal="Trả về JSON, key là tên mới, value là tên chính tắc. Nếu là mới, value là chính nó.",
            output_format='```json\n{"Tên mới 1": "Tên chính tắc", "Tên mới 2": "Tên mới 2"}\n```'
        ).build()
        ai_resolution_map = self._call_ai_with_json_parsing(prompt)
        if ai_resolution_map:
            for name, canon in ai_resolution_map.items():
                resolution_map[name] = canon
                self.resolution_cache[name] = canon
        else:
            for item in batch_to_verify: resolution_map[item["new_name"]] = item["new_name"]
        return resolution_map

    def _update_graph_with_resolution(self, nodes: Dict, edges: List, resolution_map: Dict) -> Tuple[Dict, List]:
        logger.info("Cập nhật đồ thị với kết quả đồng nhất...")
        resolved_nodes, alias_map = {}, {}
        for name, data in nodes.items():
            canonical_name = resolution_map.get(name, name)
            alias_map[name] = canonical_name
            if canonical_name not in resolved_nodes:
                resolved_nodes[canonical_name] = {"class_id": data.get('class_id'), "aliases": set()}
            if name != canonical_name: resolved_nodes[canonical_name]["aliases"].add(name)
        
        resolved_edges = []
        for edge in edges:
            source, target = alias_map.get(edge['source']), alias_map.get(edge['target'])
            if source != target: resolved_edges.append({"source": source, "target": target, "id": edge['id']})

        for name in resolved_nodes: resolved_nodes[name]["aliases"] = list(resolved_nodes[name]["aliases"])
        logger.info(f"Đồ thị sau đồng nhất: {len(resolved_nodes)} nodes, {len(resolved_edges)} edges.")
        return resolved_nodes, resolved_edges

    def _link_event_clusters(self, final_nodes: Dict[str, Any], onto: Any, ontology_path: str, info_block: str, source_identifier: str):
        """
        Bước hậu xử lý: Tìm và liên kết các cụm sự kiện có liên quan.
        """
        logger.info(f"--- Bắt đầu Bước 7: Liên kết các cụm sự kiện cho file '{source_identifier}' ---")
        
        event_class = onto.search_one(iri="*SuKien")
        if not event_class:
            logger.warning("Không tìm thấy class 'SuKien' trong ontology. Bỏ qua bước liên kết sự kiện.")
            return

        event_nodes = {name: data for name, data in final_nodes.items() if onto.search_one(iri=f"*{data['class_id']}") and issubclass(onto.search_one(iri=f"*{data['class_id']}"), event_class)}
        
        if len(event_nodes) < 2:
            logger.info("Không đủ sự kiện để liên kết. Bỏ qua.")
            return

        event_participants = {}
        for event_name in event_nodes.keys():
            query = "MATCH (p:Instance)-[]->(e:Instance {name: $event_name}) RETURN p.name AS participant_name"
            records = self.neo4j_handler._execute_query(query, {"event_name": event_name})
            event_participants[event_name] = {record["participant_name"] for record in records}
        
        candidate_pairs = []
        for event1, event2 in itertools.combinations(event_participants.keys(), 2):
            if event_participants[event1].intersection(event_participants[event2]):
                candidate_pairs.append({
                    "event_1": {"name": event1, "participants": list(event_participants[event1])},
                    "event_2": {"name": event2, "participants": list(event_participants[event2])}
                })
        
        if not candidate_pairs:
            logger.info("Không tìm thấy cặp sự kiện nào có điểm chung. Hoàn tất.")
            return
            
        logger.info(f"Tìm thấy {len(candidate_pairs)} cặp sự kiện tiềm năng để liên kết. Gửi đến AI...")
        
        prompt = Prompt(
            task_description="Phân tích các cặp sự kiện và suy luận mối quan hệ logic (thời gian, nhân quả,...) giữa chúng.",
            context=f"Toàn bộ ngữ cảnh văn bản:\n```text\n{info_block}\n```",
            input_data=f"Các cặp sự kiện cần phân tích:\n{json.dumps(candidate_pairs, ensure_ascii=False, indent=2)}",
            goal="Trả về một danh sách các liên kết có ý nghĩa giữa các sự kiện.",
            output_format="""Chỉ trả về JSON.
```json
{
  "event_links": [
    {"source_event": "tên_event_nguồn", "relation_id": "IDQuanHe", "target_event": "tên_event_đích", "reasoning": "giải thích ngắn gọn"}
  ]
}
```""",
            constraints="Chỉ tạo liên kết nếu có bằng chứng rõ ràng trong ngữ cảnh. Sử dụng các ID quan hệ như 'dienRaTruoc', 'laNguyenNhanCua', 'lienQuanDen'."
        ).build()
        
        linking_results = self._call_ai_with_json_parsing(prompt)
        if not (linking_results and "event_links" in linking_results):
            logger.warning("AI không trả về được liên kết sự kiện nào.")
            return

        new_rels_def = []
        schema_rels = {r['id'] for r in self._get_schema_from_ontology(onto)['relations']}
        for link in linking_results["event_links"]:
            if link['relation_id'] not in schema_rels:
                new_rels_def.append({"id": link['relation_id'], "label": link['relation_id'], "domain": "SuKien", "range": "SuKien"})
                schema_rels.add(link['relation_id'])

        if new_rels_def:
            logger.info(f"Phát hiện các loại quan hệ sự kiện mới: {[r['id'] for r in new_rels_def]}. Cập nhật ontology...")
            update_ontology_with_definitions(onto, [], {}, new_rels_def)
            # <<< Dòng code bị lỗi nằm ở đây >>>
            save_ontology(onto, ontology_path)
        
        rels_to_store = []
        for link in linking_results["event_links"]:
            rel_obj = onto.search_one(iri=f"*{link['relation_id']}")
            if not rel_obj: continue
            rel_label = getattr(rel_obj.label, "first", lambda: link['relation_id'])()
            rel_unique_id = re.sub(r'\W+', '_', f"{link['source_event']}_{link['relation_id']}_{link['target_event']}".lower())
            rels_to_store.append((link['source_event'], rel_label, link['target_event'], rel_unique_id))
        
        if rels_to_store:
            self.neo4j_handler.store_relationships(rels_to_store, known_entity_names=set(final_nodes.keys()))
        logger.info(f"✅ Đã thêm {len(rels_to_store)} liên kết giữa các sự kiện.")

    def process_extracted_info_to_graph(self, extracted_info_list: List[str], ontology_path: str, source_identifier: str = "unknown_source") -> bool:
        if not extracted_info_list: return True
        onto = load_ontology(ontology_path)
        if not onto: return False
        logger.info(f"--- Bắt đầu xử lý Event-Centric cho file: {source_identifier} ---")
        
        initial_nodes, initial_edges = {}, []
        for fact in extracted_info_list:
            if not fact.strip(): continue
            fragment = self._model_fact_as_event(fact, onto)
            if not (fragment and fragment.get("event") and fragment.get("participants")): continue
            event_name = f"{fragment['event']['name']}_{source_identifier}_{len(initial_edges)}"
            initial_nodes[event_name] = {"class_id": fragment['event']["class_id"]}
            for part in fragment["participants"]:
                if not all(k in part for k in ["name", "class_id", "relation_to_event"]): continue
                if part["name"] not in initial_nodes: initial_nodes[part["name"]] = {"class_id": part["class_id"]}
                initial_edges.append({"source": part["name"], "target": event_name, "id": part["relation_to_event"]})

        if not initial_nodes:
            logger.warning(f"Không mô hình hóa được node/sự kiện nào từ '{source_identifier}'.")
            return True

        existing_alias_map = self.neo4j_handler.get_all_entities_with_aliases()
        resolution_map = self._resolve_entities_in_batch(initial_nodes, existing_alias_map)
        final_nodes, final_edges = self._update_graph_with_resolution(initial_nodes, initial_edges, resolution_map)

        entities_to_store = []
        for name, data in final_nodes.items():
            cls_obj = onto.search_one(iri=f"*{data['class_id']}")
            class_label = getattr(cls_obj.label, "first", lambda: data['class_id'])() if cls_obj else data['class_id']
            existing_node_aliases = set(existing_alias_map.get(name, []))
            new_aliases = set(data.get('aliases', []))
            all_aliases = list(existing_node_aliases.union(new_aliases))
            entities_to_store.append({"name": name, "class_label": class_label, "class_id": data['class_id'], "aliases": all_aliases})
        
        if entities_to_store: self.neo4j_handler.store_entities(entities_to_store)
        
        rels_to_store = []
        for edge in final_edges:
            rel_obj = onto.search_one(iri=f"*{edge['id']}")
            if not rel_obj: continue
            relation_label = getattr(rel_obj.label, "first", lambda: edge['id'])()
            rel_unique_id = re.sub(r'\W+', '_', f"{edge['source']}_{edge['id']}_{edge['target']}".lower())
            rels_to_store.append((edge['source'], relation_label, edge['target'], rel_unique_id))
        
        if rels_to_store:
            self.neo4j_handler.store_relationships(rels_to_store, known_entity_names=set(final_nodes.keys()))

        self._save_cache()
        logger.info(f"Đã lưu đồ thị ban đầu vào Neo4j cho '{source_identifier}'.")
        
        # <<< SỬA LỖI Ở ĐÂY: Thêm 'ontology_path' vào lời gọi hàm >>>
        info_block = "\n".join(f"- {item}" for item in extracted_info_list)
        self._link_event_clusters(final_nodes, onto, ontology_path, info_block, source_identifier)

        logger.info(f"✅ Hoàn tất toàn bộ quá trình xử lý cho '{source_identifier}'.")
        return True