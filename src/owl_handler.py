# File: src/owl_handler.py
import os
import re
import logging
import types # Sử dụng cho types.new_class
from owlready2 import get_ontology, Thing, ObjectProperty, DataProperty, sync_reasoner_pellet
from typing import List, Dict, Optional, Tuple, Any, Set, Type # Cho type hinting

# --- Cấu hình Logger cho module này ---
logger = logging.getLogger(__name__)
# Nếu không có cấu hình logging nào ở main, thiết lập một cấu hình cơ bản
if not logger.handlers:
    logger.setLevel(logging.INFO) # Mặc định INFO, có thể thay đổi
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    # logger.propagate = False # Nếu không muốn truyền lên root logger

# --- Namespace và các hằng số ---
DEFAULT_ONTOLOGY_NAMESPACE = "http://example.org/ontology#" #

# Định nghĩa các kiểu dữ liệu XSD mà Owlready2 hỗ trợ ánh xạ trực tiếp
DATATYPE_MAP = {
    "string": str,
    "str": str,
    "int": int,
    "integer": int,
    "float": float,
    "double": float,
    "boolean": bool,
    "bool": bool,
    # Thêm các kiểu khác nếu cần, ví dụ: date, dateTime
    # from datetime import date, datetime
    # "date": date,
    # "dateTime": datetime,
}

# --- Các hàm tiện ích ---
def parse_id_label_line(line: str) -> Tuple[Optional[str], Optional[str]]: #
    """
    Phân tích một dòng có định dạng "- id: ClassID | label: Class Label".
    Trả về (id, label) hoặc (None, None) nếu phân tích thất bại.
    """
    match = re.match(r"-?\s*id:\s*([^\|]+)\|\s*label:\s*(.+)", line) #
    if match:
        return match.group(1).strip(), match.group(2).strip() #
    return None, None #

def _get_owl_entity(onto: Any, entity_name: str, entity_type: Type) -> Optional[Any]:
    """
    Hàm nội bộ để lấy một entity (class, property) từ ontology theo tên.
    Sử dụng IRI đầy đủ nếu namespace của ontology được biết.
    """
    # Thử tìm bằng tên đầy đủ (IRI) trước
    full_iri = onto.base_iri + entity_name
    entity = onto.search_one(iri=full_iri)
    if entity and isinstance(entity, entity_type):
        return entity
    # Nếu không tìm thấy, thử tìm bằng tên (có thể khớp một phần cuối IRI)
    # Điều này hữu ích nếu entity_name không bao gồm namespace
    entity = onto.search_one(iri=f"*{entity_name}")
    if entity and isinstance(entity, entity_type):
        return entity
    return None

# --- Các hàm chính xử lý Ontology ---
def load_ontology(owl_file_path: str) -> Optional[Any]: #
    """Tải một file OWL từ đường dẫn được cung cấp."""
    if not os.path.exists(owl_file_path): #
        logger.warning(f"File OWL không tìm thấy để tải: {owl_file_path}") #
        return None #
    
    abs_owl_path = os.path.abspath(owl_file_path) #
    try:
        onto = get_ontology(f"file://{abs_owl_path}").load() #
        logger.info(f"Ontology đã được tải thành công từ: {owl_file_path}") #
        return onto #
    except Exception as e:
        logger.error(f"Lỗi khi tải ontology từ {owl_file_path}: {e}", exc_info=True) #
        return None #

def save_ontology(onto: Any, owl_file_path: str, rdf_format: str = "rdfxml") -> bool: #
    """Lưu ontology vào đường dẫn được cung cấp."""
    if not onto:
        logger.error("Không thể lưu ontology, đối tượng ontology là None.")
        return False
    try:
        # Đảm bảo thư mục lưu file tồn tại
        output_dir = os.path.dirname(owl_file_path)
        if output_dir: # Nếu owl_file_path không chỉ là tên file
            os.makedirs(output_dir, exist_ok=True)
            
        onto.save(file=owl_file_path, format=rdf_format) #
        logger.info(f"Ontology đã được lưu thành công vào: {owl_file_path}") #
        return True
    except Exception as e:
        logger.error(f"Lỗi khi lưu ontology vào {owl_file_path}: {e}", exc_info=True) #
        return False

def run_reasoner(onto: Any, infer_property_values: bool = True, infer_data_property_values: bool = True) -> bool: #
    """Chạy Pellet reasoner trên ontology."""
    if onto: #
        try:
            with onto: #
                sync_reasoner_pellet(infer_property_values=infer_property_values, infer_data_property_values=infer_data_property_values) #
            logger.info("Reasoner (Pellet) đã thực thi thành công.") #
            return True
        except Exception as e: #
            if "java" in str(e).lower() or "jdk" in str(e).lower() or "jre" in str(e).lower(): #
                 logger.warning(f"Lỗi khi chạy Pellet reasoner: {e}. " #
                                 "Điều này có thể do Java (JDK/JRE) chưa được cấu hình đúng hoặc Pellet không tìm thấy. " #
                                 "Các thao tác ontology sẽ tiếp tục mà không có reasoning.") #
            else: #
                logger.warning(f"Lỗi khi chạy Pellet reasoner: {e}. Các thao tác ontology sẽ tiếp tục mà không có reasoning.") #
            return False
    else: #
        logger.warning("Đối tượng Ontology là None. Không thể chạy reasoner.") #
        return False

def _create_or_update_classes(onto: Any, class_definitions: List[Dict[str, str]], class_map: Dict[str, Any]) -> None:
    """Tạo hoặc cập nhật classes trong ontology."""
    for c_def in class_definitions:
        class_id, class_label = c_def.get("id"), c_def.get("label")
        if not (class_id and class_label): # Bỏ qua nếu thiếu id hoặc label
            logger.warning(f"Bỏ qua class do thiếu ID hoặc Label: {c_def}")
            continue

        owl_cls = class_map.get(class_id) or _get_owl_entity(onto, class_id, Thing)
        if owl_cls: # Class đã tồn tại, cập nhật label
            if class_label not in owl_cls.label:
                owl_cls.label.append(class_label) # Owlready2 quản lý label như một list
                logger.debug(f"Đã cập nhật label cho class '{class_id}' thành '{class_label}'.")
        else: # Tạo class mới
            owl_cls = types.new_class(class_id, (Thing,)) #
            owl_cls.label = [class_label] #
            logger.debug(f"Đã tạo class mới: '{class_id}' với label '{class_label}'.")
        class_map[class_id] = owl_cls #

def _create_or_update_datatype_properties(onto: Any, prop_definitions: Dict[str, List[Dict[str, str]]], class_map: Dict[str, Any]) -> None:
    """Tạo hoặc cập nhật data properties."""
    for class_id_str, props_list in prop_definitions.items(): #
        domain_class_obj = class_map.get(class_id_str) #
        if not domain_class_obj: #
            logger.warning(f"Không tìm thấy domain class '{class_id_str}' khi tạo data properties. Bỏ qua các properties cho class này.")
            continue
            
        for p_def in props_list: #
            prop_id, prop_label = p_def.get("id"), p_def.get("label") #
            prop_type_str = p_def.get("type", "string").lower() # Mặc định kiểu string, chuẩn hóa lowercase

            if not (prop_id and prop_label): # Bỏ qua nếu thiếu id hoặc label
                logger.warning(f"Bỏ qua data property do thiếu ID hoặc Label: {p_def} cho class '{class_id_str}'.")
                continue

            dp = _get_owl_entity(onto, prop_id, DataProperty)
            if not dp: # Tạo mới nếu chưa có
                dp = types.new_class(prop_id, (DataProperty,)) #
                dp.label = [prop_label] #
                logger.debug(f"Đã tạo data property mới: '{prop_id}' với label '{prop_label}'.")
            elif prop_label not in dp.label: # Cập nhật label nếu đã có property
                dp.label.append(prop_label)
                logger.debug(f"Đã cập nhật label cho data property '{prop_id}' thành '{prop_label}'.")

            # Gán domain
            if domain_class_obj not in dp.domain: #
                dp.domain.append(domain_class_obj) #
                logger.debug(f"Đã thêm domain '{class_id_str}' cho data property '{prop_id}'.")
            
            # Gán range (kiểu dữ liệu)
            prop_type = DATATYPE_MAP.get(prop_type_str, str) # Mặc định là str nếu kiểu không được hỗ trợ
            if prop_type not in dp.range: #
                # Owlready2 có thể chỉ cho phép một range cho DataProperty.
                # Nếu đã có range khác, có thể cần xóa range cũ hoặc không thêm range mới.
                # Hiện tại, chúng ta thêm nếu chưa có.
                if not dp.range: # Chỉ thêm nếu range rỗng
                    dp.range.append(prop_type) #
                    logger.debug(f"Đã thêm range '{prop_type_str}' cho data property '{prop_id}'.")
                elif prop_type not in dp.range: # Nếu range đã có và khác, log cảnh báo
                     logger.warning(f"Data property '{prop_id}' đã có range {dp.range}. Không thêm range mới '{prop_type_str}'.")


def _create_or_update_object_properties(onto: Any, rel_definitions: List[Dict[str, str]], class_map: Dict[str, Any]) -> None:
    """Tạo hoặc cập nhật object properties."""
    for r_def in rel_definitions: #
        rel_id, rel_label = r_def.get("id"), r_def.get("label") #
        domain_id_str, range_id_str = r_def.get("domain"), r_def.get("range") #

        if not (rel_id and rel_label and domain_id_str and range_id_str): #
            logger.warning(f"Bỏ qua object property do thiếu ID, Label, Domain hoặc Range: {r_def}")
            continue

        domain_class_obj = class_map.get(domain_id_str) #
        range_class_obj = class_map.get(range_id_str) #

        if not (domain_class_obj and range_class_obj): #
            logger.warning(f"Không tìm thấy domain ('{domain_id_str}') hoặc range ('{range_id_str}') class cho object property '{rel_id}'. Bỏ qua.")
            continue
            
        op = _get_owl_entity(onto, rel_id, ObjectProperty)
        if not op: # Tạo mới nếu chưa có
            op = types.new_class(rel_id, (ObjectProperty,)) #
            op.label = [rel_label] #
            logger.debug(f"Đã tạo object property mới: '{rel_id}' với label '{rel_label}'.")
        elif rel_label not in op.label: # Cập nhật label nếu đã có property
            op.label.append(rel_label)
            logger.debug(f"Đã cập nhật label cho object property '{rel_id}' thành '{rel_label}'.")

        # Gán domain
        if domain_class_obj not in op.domain: #
            op.domain.append(domain_class_obj) #
            logger.debug(f"Đã thêm domain '{domain_id_str}' cho object property '{rel_id}'.")
        
        # Gán range
        if range_class_obj not in op.range: #
            op.range.append(range_class_obj) #
            logger.debug(f"Đã thêm range '{range_id_str}' cho object property '{rel_id}'.")


def create_ontology_from_definitions(
    class_definitions: List[Dict[str, str]],
    prop_definitions: Dict[str, List[Dict[str, str]]],
    rel_definitions: List[Dict[str, str]],
    output_dir: str,
    owl_filename: str,
    ns: str = DEFAULT_ONTOLOGY_NAMESPACE
) -> Tuple[Optional[str], Optional[Any]]: #
    """
    Xây dựng một ontology OWL từ các định nghĩa văn bản đã phân tích và lưu nó.
    Args:
        class_definitions (list): List của dicts, ví dụ: [{"id": "ClassID", "label": "Class Label"}, ...]
        prop_definitions (dict): Dict ánh xạ class_id tới list các props,
                                 ví dụ: {"ClassID": [{"id": "propID", "label": "Prop Label", "type": "string"}, ...]}
        rel_definitions (list): List của dicts cho relationships,
                                ví dụ: [{"id": "relID", "label": "Rel Label", "domain": "DomainClassID", "range": "RangeClassID"}, ...]
        output_dir (str): Thư mục để lưu file OWL.
        owl_filename (str): Tên của file OWL.
        ns (str): Namespace cho ontology.
    Returns:
        Tuple[Optional[str], Optional[Any]]: Đường dẫn đến file OWL đã lưu và đối tượng ontology, hoặc (None, None) nếu lỗi.
    """
    logger.info(f"Bắt đầu tạo ontology mới với namespace: {ns}")
    owl_file_path = os.path.join(output_dir, owl_filename) #
    onto = get_ontology(ns) #
    # class_map_owl_objects dùng để lưu trữ {class_id_str: owl_class_object}
    # để đảm bảo các class được tham chiếu đúng cách khi tạo properties.
    class_map_owl_objects: Dict[str, Any] = {} 

    with onto: #
        _create_or_update_classes(onto, class_definitions, class_map_owl_objects)
        _create_or_update_datatype_properties(onto, prop_definitions, class_map_owl_objects)
        _create_or_update_object_properties(onto, rel_definitions, class_map_owl_objects)

    if save_ontology(onto, owl_file_path):
        logger.info(f"Ontology mới đã được tạo và lưu tại: {owl_file_path}")
        run_reasoner(onto) # Chạy reasoner sau khi tạo và lưu lần đầu
        return owl_file_path, onto #
    else:
        logger.error(f"Không thể lưu ontology mới tại: {owl_file_path}")
        return None, None


def update_ontology_with_definitions(
    onto: Any,
    class_definitions: List[Dict[str, str]],
    prop_definitions: Dict[str, List[Dict[str, str]]],
    rel_definitions: List[Dict[str, str]],
    save_path: Optional[str] = None
) -> bool: #
    """
    Cập nhật một đối tượng ontology hiện có với các định nghĩa mới.
    Hàm này sẽ cố gắng thêm class/property mới hoặc cập nhật label/domain/range
    của những cái đã tồn tại nếu cần.

    Args:
        onto (Ontology): Đối tượng ontology để cập nhật.
        class_definitions (list): Định nghĩa class mới hoặc cần cập nhật.
        prop_definitions (dict): Định nghĩa property mới hoặc cần cập nhật.
        rel_definitions (list): Định nghĩa relation mới hoặc cần cập nhật.
        save_path (Optional[str]): Đường dẫn để lưu ontology sau khi cập nhật. Nếu None, ontology không được lưu.

    Returns:
        bool: True nếu ontology được cập nhật thành công (và lưu nếu có save_path), False nếu có lỗi.
    """
    if not onto: #
        logger.error("Không thể cập nhật ontology, đối tượng ontology là None.") #
        return False #

    logger.info(f"Bắt đầu cập nhật ontology: {onto.base_iri}")
    
    # Xây dựng map ban đầu của các class hiện có trong ontology
    class_map_owl_objects: Dict[str, Any] = {cls.name: cls for cls in onto.classes()} #

    anything_changed = False # Cờ để theo dõi xem có thay đổi thực sự nào không

    # Để theo dõi số lượng phần tử trước và sau khi thêm/cập nhật
    initial_counts = {
        "classes": len(list(onto.classes())),
        "data_properties": len(list(onto.data_properties())),
        "object_properties": len(list(onto.object_properties()))
    }

    with onto: #
        _create_or_update_classes(onto, class_definitions, class_map_owl_objects)
        _create_or_update_datatype_properties(onto, prop_definitions, class_map_owl_objects)
        _create_or_update_object_properties(onto, rel_definitions, class_map_owl_objects)

    # Kiểm tra xem có sự thay đổi về số lượng không
    final_counts = {
        "classes": len(list(onto.classes())),
        "data_properties": len(list(onto.data_properties())),
        "object_properties": len(list(onto.object_properties()))
    }

    if (final_counts["classes"] > initial_counts["classes"] or
        final_counts["data_properties"] > initial_counts["data_properties"] or
        final_counts["object_properties"] > initial_counts["object_properties"]):
        anything_changed = True
        logger.info("Có sự thay đổi về số lượng thực thể trong ontology sau khi cập nhật.")
    else:
        # Logic kiểm tra label/domain/range thay đổi phức tạp hơn, có thể thêm nếu cần.
        # Hiện tại, chỉ dựa vào số lượng.
        logger.info("Không có sự thay đổi về số lượng thực thể chính sau khi cập nhật (có thể label/domain/range đã được cập nhật).")


    if save_path:
        if save_ontology(onto, save_path):
            logger.info(f"Ontology đã cập nhật và được lưu tại: {save_path}")
            run_reasoner(onto) # Chạy reasoner sau khi cập nhật và lưu
        else:
            logger.error(f"Không thể lưu ontology đã cập nhật tại: {save_path}")
            return False # Lỗi lưu file
            
    elif anything_changed: # Nếu có thay đổi nhưng không lưu, có thể cần chạy reasoner
        logger.info("Ontology đã được cập nhật trong bộ nhớ. Chạy reasoner (nếu cần).")
        run_reasoner(onto)

    logger.info("Hoàn tất quá trình cập nhật ontology.") #
    return True #
