import json
import logging
import os
import re
from typing import Any

from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import (  # type: ignore[import-not-found] 
        MarkdownTextSplitter,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_ollama_llm() -> ChatOllama:
    """
    Initialize the local ChatOllama client.
    """
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        temperature=0.0,
    )


def get_ollama_embeddings() -> OllamaEmbeddings:
    """
    Initialize the local OllamaEmbeddings client.
    """
    return OllamaEmbeddings(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_EMBEDDING_MODEL,
    )


def get_tenant_vector_store(tenant_id: str) -> Chroma:
    """
    Get or create a tenant-specific Chroma vector store.
    """
    persist_dir = os.path.join(settings.CHROMA_DATA_DIR, tenant_id)
    embeddings = get_ollama_embeddings()
    return Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
        collection_name="documents",
    )


def index_document_to_vector_store(tenant_id: str, doc_id: str, content: str) -> None:
    """
    Chunk the document content and index it to the tenant's vector store,
    prepending 'search_document: ' to the text of each chunk.
    """
    # 1. Split the document content (chunk size 1000, overlap 200)
    splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(content)

    if not chunks:
        return

    # 2. Prepend "search_document: " to the text
    prepended_chunks = [f"search_document: {chunk}" for chunk in chunks]
    metadatas = [{"doc_id": str(doc_id)} for _ in chunks]

    # 3. Save to vector store (clear existing first)
    vector_store = get_tenant_vector_store(tenant_id)
    delete_document_from_vector_store(tenant_id, doc_id)
    vector_store.add_texts(texts=prepended_chunks, metadatas=metadatas)


def delete_document_from_vector_store(tenant_id: str, doc_id: str) -> None:
    """
    Delete indexed document chunks from the tenant's vector store.
    """
    vector_store = get_tenant_vector_store(tenant_id)
    try:
        results = vector_store.get(where={"doc_id": str(doc_id)})
        if results and "ids" in results and results["ids"]:
            vector_store.delete(ids=results["ids"])
    except Exception as e:
        logger.error(f"Error deleting from vector store: {e}")


def query_document_vector_store(tenant_id: str, doc_id: str, query: str) -> list[str]:
    """
    Query the vector store for relevant chunks, prepending 'search_query: '
    to the user's question, and removing 'search_document: ' from the retrieved chunks.
    """
    vector_store = get_tenant_vector_store(tenant_id)
    prepended_query = f"search_query: {query}"

    try:
        docs = vector_store.similarity_search(
            query=prepended_query,
            k=4,
            filter={"doc_id": str(doc_id)}
        )

        retrieved_texts = []
        for doc in docs:
            text = doc.page_content
            if text.startswith("search_document: "):
                text = text[len("search_document: "):]
            retrieved_texts.append(text)
        return retrieved_texts
    except Exception as e:
        logger.error(f"Error querying vector store: {e}")
        return []


def review_document(title: str, content: str) -> dict[str, Any]:
    """
    Accuracy Reviewer Agent: Analyzes the document, checks for errors,
    and returns a structured report.
    """
    llm = get_ollama_llm()

    system_prompt = (
        "You are an expert Document Accuracy Reviewer agent.\n"
        "Your task is to analyze the markdown document provided, verify its accuracy, "
        "identify errors, logic flaws, or grammatical issues, and suggest specific improvements.\n\n"
        "You MUST respond ONLY with a JSON object in this format:\n"
        "{{\n"
        '  "is_accurate": true or false,\n'
        '  "report": "detailed markdown string describing issues and suggesting changes"\n'
        "}}\n"
        "Do not wrap your output in conversational filler. Only return the JSON."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", "Document Title: {title}\n\nDocument Content:\n{content}"),
        ]
    )

    chain = prompt | llm

    try:
        response = chain.invoke({"title": title, "content": content})
        response_text = str(response.content).strip()

        # Extract JSON using regex in case model wraps it in markdown backticks
        json_match = re.search(r"(\{.*\})", response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            data = json.loads(response_text)

        return {
            "is_accurate": bool(data.get("is_accurate", True)),
            "report": str(data.get("report", "Accuracy analysis complete.")),
        }
    except Exception as e:
        return {
            "is_accurate": False,
            "report": f"Failed to complete accuracy check. Agent response was unparseable. Error: {str(e)}",
        }


def chat_with_document(query: str, doc_title: str, doc_chunks: list[str]) -> str:
    """
    Chatbot Agent: Answers questions about a document using retrieved context chunks.
    """
    llm = get_ollama_llm()

    # Combine retrieved chunks as the context
    context = "\n\n---\n\n".join(doc_chunks) if doc_chunks else "Δεν βρέθηκαν σχετικά αποσπάσματα στο έγγραφο."

    system_prompt = (
        "Είσαι ένας βοηθός τεχνητής νοημοσύνης (chatbot).\n"
        "Πρέπει να απαντάς ΠΑΝΤΑ και ΑΠΟΚΛΕΙΣΤΙΚΑ στα Ελληνικά (χρησιμοποιώντας το ελληνικό αλφάβητο), "
        "ακόμη και αν η ερώτηση ή το έγγραφο είναι σε άλλη γλώσσα.\n\n"
        "Απαντάς σε ερωτήσεις του χρήστη με βάση το ακόλουθο έγγραφο: '{title}'.\n"
        "Χρησιμοποίησε τα παρακάτω σχετικά αποσπάσματα του εγγράφου ως πηγή για να απαντήσεις. "
        "Δώσε ιδιαίτερη προσοχή σε όλες τις λεπτομέρειες του κειμένου, ακόμη και σε πληροφορίες που βρίσκονται μέσα σε παρενθέσεις (...) ή επεξηγήσεις, "
        "καθώς μπορεί να περιέχουν σημαντικές απαντήσεις.\n\n"
        "Να είσαι βοηθητικός, φιλικός και να απαντάς με ακρίβεια βασιζόμενος αποκλειστικά στα παρεχόμενα αποσπάσματα.\n\n"
        "Σχετικά Αποσπάσματα Εγγράφου:\n"
        "{context}"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", "{query}"),
        ]
    )

    chain = prompt | llm

    try:
        response = chain.invoke(
            {"title": doc_title, "context": context, "query": query}
        )
        return str(response.content)
    except Exception as e:
        return f"Error interacting with chatbot agent: {str(e)}"
