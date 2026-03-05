from pydantic import BaseModel
from typing import List, Optional


class AssignmentCreate(BaseModel):
    """Teacher creates an assignment — just needs a title. ID is auto-assigned."""
    title: str


class SubmissionCreate(BaseModel):
    """Student submits text. student_id comes from the auth token, not the body."""
    assignment_id: int
    text: str


class MatchResponse(BaseModel):
    input_sentence: str
    matched_sentence: str
    student_id: int
    similarity: float

    class Config:
        from_attributes = True


class SubmissionResponse(BaseModel):
    id: int
    student_id: int
    assignment_id: int
    plagiarism_percentage: float

    class Config:
        from_attributes = True


class SubmissionDetailResponse(BaseModel):
    submission: SubmissionResponse
    matches: List[MatchResponse]

    class Config:
        from_attributes = True


class AssignmentResponse(BaseModel):
    id: int
    title: str
    teacher_id: int

    class Config:
        from_attributes = True