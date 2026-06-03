from pydantic import BaseModel


class UploadData(BaseModel):
    filename: str
    chunks: int


class UploadResponse(BaseModel):
    success: bool
    message: str
    data: UploadData | None = None


class DocumentItem(BaseModel):
    filename: str
    uploaded_at: str


class DocumentsData(BaseModel):
    documents: list[DocumentItem]


class DocumentsResponse(BaseModel):
    success: bool
    message: str
    data: DocumentsData | None = None
