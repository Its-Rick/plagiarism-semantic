from pydantic import BaseModel

class AssignmentRequest(BaseModel):
    student_id: int
    assignment_id: int
    text: str