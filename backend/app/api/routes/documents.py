import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request, status
from sqlmodel import func, select

from app.agents import (
    chat_with_document,
    review_document,
    index_document_to_vector_store,
    delete_document_from_vector_store,
    query_document_vector_store,
)
from app.api.deps import CurrentUser, SessionDep, resolve_tenant_id
from app.models import Document, DocumentPublic, DocumentsPublic, Message

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentPublic, status_code=201)
async def upload_document(
    *,
    session: SessionDep,
    request: Request,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    title: str | None = Form(None),
) -> Any:
    """
    Upload a markdown document. The document will be saved and reviewed
    by the Accuracy Reviewer Agent using local Gemma via Ollama, and then
    indexed into the tenant-specific Chroma vector store.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided."
        )

    # Read markdown contents
    contents_bytes = await file.read()
    try:
        contents_str = contents_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content must be UTF-8 encoded text.",
        )

    doc_title = title or file.filename.rsplit(".", 1)[0]

    # Create the draft document record
    db_doc = Document(
        title=doc_title,
        content=contents_str,
        owner_id=current_user.id,
    )
    session.add(db_doc)
    session.commit()
    session.refresh(db_doc)

    # Trigger Accuracy Reviewer Agent (local Gemma)
    review_result = review_document(title=db_doc.title, content=db_doc.content)

    # Update document with review results
    db_doc.is_accurate = review_result.get("is_accurate", False)
    db_doc.accuracy_report = review_result.get("report", "No report generated.")
    session.add(db_doc)
    session.commit()
    session.refresh(db_doc)

    # Index the document chunks in the tenant's vector store
    tenant_id = resolve_tenant_id(request)
    try:
        index_document_to_vector_store(tenant_id=tenant_id, doc_id=db_doc.id, content=db_doc.content)
    except Exception as e:
        print(f"Error indexing document to vector store: {e}")

    return db_doc


@router.get("/", response_model=DocumentsPublic)
def read_documents(
    session: SessionDep,
    _current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve documents uploaded by users of the current tenant.
    """
    # Filter documents owned by the current tenant (since user is tenant-scoped)
    count_statement = select(func.count()).select_from(Document)
    count = session.exec(count_statement).one()

    statement = select(Document).offset(skip).limit(limit)
    documents = session.exec(statement).all()

    return DocumentsPublic(data=documents, count=count)


@router.get("/{doc_id}", response_model=DocumentPublic)
def read_document_by_id(
    *,
    session: SessionDep,
    _current_user: CurrentUser,
    doc_id: uuid.UUID,
) -> Any:
    """
    Retrieve details of a specific document, including its accuracy report.
    """
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
    return doc


@router.post("/{doc_id}/chat", response_model=Message)
def chat_about_document(
    *,
    session: SessionDep,
    request: Request,
    _current_user: CurrentUser,
    doc_id: uuid.UUID,
    payload: dict[str, str],
) -> Any:
    """
    Ask the chatbot agent a question regarding the contents of the document.
    Relevant chunks are retrieved using semantic similarity from Chroma.
    """
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )

    query = payload.get("query")
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'query' is required in JSON payload.",
        )

    # Resolve tenant and retrieve relevant document chunks via semantic search
    tenant_id = resolve_tenant_id(request)
    try:
        chunks = query_document_vector_store(tenant_id=tenant_id, doc_id=doc_id, query=query)
    except Exception as e:
        print(f"Error querying vector store: {e}")
        chunks = []

    # Trigger Chatbot Agent (local Gemma) with context chunks
    reply = chat_with_document(query=query, doc_title=doc.title, doc_chunks=chunks)
    return Message(message=reply)


@router.delete("/{doc_id}", response_model=Message)
def delete_document(
    *,
    session: SessionDep,
    request: Request,
    _current_user: CurrentUser,
    doc_id: uuid.UUID,
) -> Any:
    """
    Delete a document and its indexed vector store chunks.
    """
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )

    # Delete indexed chunks from the tenant's vector store
    tenant_id = resolve_tenant_id(request)
    try:
        delete_document_from_vector_store(tenant_id=tenant_id, doc_id=doc_id)
    except Exception as e:
        print(f"Error deleting document from vector store: {e}")

    session.delete(doc)
    session.commit()
    return Message(message="Document deleted successfully.")
