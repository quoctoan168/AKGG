# File: src/neo4j_handler.py (Đã cập nhật để lưu aliases)
import logging
from typing import List, Tuple, Set, Optional, Dict, Any
from neo4j import GraphDatabase, Driver

try:
    from config import settings
except ImportError:
    print("CẢNH BÁO: config.settings không tìm thấy. Neo4jHandler có thể cần thông tin kết nối được truyền trực tiếp.")
    settings = None

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class Neo4jHandler:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        db_uri, db_user, db_password = uri, user, password
        if settings:
            db_uri = uri or getattr(settings, 'NEO4J_URI', None)
            db_user = user or getattr(settings, 'NEO4J_USER', None)
            db_password = password or getattr(settings, 'NEO4J_PASSWORD', None)

        if not all([db_uri, db_user, db_password]):
            logger.error("❌ Thông tin kết nối Neo4j (URI, user, password) chưa được cấu hình đầy đủ.")
            self.driver: Optional[Driver] = None
            return

        try:
            self.driver: Optional[Driver] = GraphDatabase.driver(db_uri, auth=(db_user, db_password))
            self.driver.verify_connectivity()
            logger.info("✅ Neo4j driver đã được khởi tạo và kết nối thành công.")
        except Exception as e:
            logger.error(f"❌ Lỗi khi khởi tạo Neo4j driver hoặc kết nối: {e}", exc_info=True)
            self.driver = None

    def close(self) -> None:
        if self.driver:
            self.driver.close()
            logger.info("ℹ️ Neo4j driver đã được đóng.")

    def _execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None, *, db: Optional[str] = None) -> List[Any]:
        if not self.driver:
            logger.error("❌ Neo4j driver chưa được khởi tạo.")
            return []
        try:
            records, _, _ = self.driver.execute_query(query, parameters, database_=db)
            return records
        except Exception as e:
            logger.error(f"❌ Lỗi khi thực thi query Neo4j: {query} | Params: {parameters} | Error: {e}", exc_info=True)
            return []

    def clear_database(self) -> bool:
        logger.info("Đang xóa toàn bộ dữ liệu trong Neo4j database...")
        self._execute_query("MATCH (n) DETACH DELETE n")
        logger.info("✅ Lệnh xóa Neo4j database đã được gửi thành công.")
        return True

    def get_all_entities_with_aliases(self) -> Dict[str, List[str]]:
        """Lấy tất cả các thực thể và danh sách tên thay thế (aliases) của chúng."""
        logger.info("Đang lấy danh sách các thực thể và aliases từ Neo4j...")
        query = "MATCH (n:Instance) RETURN n.name AS name, n.aliases AS aliases"
        results = self._execute_query(query)
        # Tạo một từ điển map mỗi alias về tên chính (canonical name)
        alias_map = {}
        for record in results:
            canonical_name = record["name"]
            alias_map[canonical_name] = canonical_name # Tên chính cũng là một alias của chính nó
            if record["aliases"]:
                for alias in record["aliases"]:
                    alias_map[alias] = canonical_name
        return alias_map


    def store_entities(self, entities_data: List[Dict[str, Any]]) -> Set[str]:
        """
        Lưu/cập nhật thực thể vào Neo4j.
        Dữ liệu đầu vào là một list các dictionary, mỗi dict chứa 'name', 'class_label', 'class_id', và 'aliases'.
        """
        if not entities_data: return set()
        
        query = """
        UNWIND $batch AS entity_props
        MERGE (n:Instance {name: entity_props.name})
        SET 
            n.class_label = entity_props.class_label,
            n.class_id = entity_props.class_id,
            n.display_name = entity_props.name,
            n.aliases = entity_props.aliases
        RETURN entity_props.name AS created_name
        """
        results = self._execute_query(query, parameters={"batch": entities_data})
        processed_names = {record["created_name"] for record in results}
        logger.info(f"✅ Entities đã được lưu/merge: {len(processed_names)}/{len(entities_data)}.")
        return processed_names

    def store_relationships(self, relationships_data: List[Tuple[str, str, str, str]], known_entity_names: Optional[Set[str]] = None) -> int:
        if not relationships_data: return 0
        processed_rels_count = 0
        for source, rel, target, rel_id in relationships_data:
            if not all([source, rel, target, rel_id]): continue
            if known_entity_names and not (source in known_entity_names and target in known_entity_names): continue
            
            clean_rel_label = rel.replace('`', '')
            query = (
                f"MATCH (a:Instance {{name: $source_name}}) "
                f"MATCH (b:Instance {{name: $target_name}}) "
                f"MERGE (a)-[r:`{clean_rel_label}`]->(b) "
                f"SET r.id = $rel_id_prop"
            )
            params = {"source_name": source, "target_name": target, "rel_id_prop": rel_id}
            self._execute_query(query, parameters=params)
            processed_rels_count += 1
        logger.info(f"✅ Relationships đã được lưu/merge: {processed_rels_count}/{len(relationships_data)}.")
        return processed_rels_count

    def find_orphan_nodes(self, node_names: List[str]) -> List[Dict[str, Any]]:
        if not node_names:
            return []
        logger.info(f"Đang tìm các node mồ côi trong số {len(node_names)} node đã xử lý...")
        query = """
        MATCH (n:Instance)
        WHERE n.name IN $names AND COUNT { (n)--() } = 0
        RETURN n.name AS name, n.class_label AS class_label, n.class_id AS class_id
        """
        results = self._execute_query(query, parameters={"names": node_names})
        orphans = [{"name": r["name"], "class_label": r["class_label"], "class_id": r["class_id"]} for r in results]
        if orphans:
            logger.warning(f"Đã tìm thấy {len(orphans)} node mồ côi: {[o['name'] for o in orphans]}")
        return orphans

    def delete_node_by_name(self, name: str) -> bool:
        """Xóa một node (và các cạnh của nó) dựa trên tên."""
        logger.warning(f"Đang yêu cầu xóa node '{name}'...")
        query = "MATCH (n:Instance {name: $name}) DETACH DELETE n"
        self._execute_query(query, parameters={"name": name})
        logger.info(f"Đã thực thi lệnh xóa cho node '{name}'.")
        return True