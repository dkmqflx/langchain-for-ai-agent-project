from pydantic import BaseModel


class UploadData(BaseModel):
    filename: str
    chunks: int


class UploadResponse(BaseModel):
    data: UploadData
    isSuccess: bool = True
    code: str = "SUCCESS"
    message: str


class DocumentItem(BaseModel):
    filename: str
    uploaded_at: str


class DocumentsData(BaseModel):
    documents: list[DocumentItem]


class DocumentsResponse(BaseModel):
    data: DocumentsData
    isSuccess: bool = True
    code: str = "SUCCESS"
    message: str
