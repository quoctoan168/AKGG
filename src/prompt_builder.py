# prompt_builder.py

class Prompt:
    def __init__(self, task_description=None, context=None, input_data=None, goal=None, output_format=None, constraints=None, instructions=None, external_link=None, file_summary_note=None):
        self.task_description = task_description
        self.context = context
        self.input_data = input_data
        self.goal = goal
        self.output_format = output_format
        self.constraints = constraints
        self.instructions = instructions
        self.external_link = external_link
        self.file_summary_note = file_summary_note

    def build(self):
        """Tạo prompt đầu vào dựa trên các thành phần."""
        sections = []

        if self.task_description:
            sections.append(f"[YÊU CẦU]\n{self.task_description}")
        if self.context:
            sections.append(f"[BỐI CẢNH]\n{self.context}")
        if self.input_data:
            sections.append(f"[DỮ LIỆU ĐẦU VÀO]\n{self.input_data}")
        if self.goal:
            sections.append(f"[MỤC TIÊU]\n{self.goal}")
        if self.output_format:
            sections.append(f"[ĐỊNH DẠNG KẾT QUẢ MONG MUỐN]\n{self.output_format}")
        if self.constraints:
            sections.append(f"[RÀNG BUỘC]\n{self.constraints}")
        if self.instructions:
            sections.append(f"[HƯỚNG DẪN XỬ LÝ]\n{self.instructions}")
        if self.external_link:
            sections.append(f"[TÀI LIỆU NGOÀI HỆ THỐNG]\nLink: {self.external_link}")
        if self.file_summary_note:
            sections.append(f"[GHI CHÚ VỀ DỮ LIỆU LỚN]\n{self.file_summary_note}")
        return "\n\n".join(sections).strip()
