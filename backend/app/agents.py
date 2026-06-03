import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from app.core.config import settings


def get_ollama_llm() -> ChatOllama:
    """
    Initialize the local ChatOllama client.
    """
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        temperature=0.0,
    )


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
        "{\n"
        '  "is_accurate": true or false,\n'
        '  "report": "detailed markdown string describing issues and suggesting changes"\n'
        "}\n"
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


def chat_with_document(query: str, doc_title: str, doc_content: str) -> str:
    """
    Chatbot Agent: Answers questions about a specific document.
    """
    llm = get_ollama_llm()

    system_prompt = (
        "You are a helpful chatbot assistant. "
        "You MUST answer the user's questions in Greek only (using the Greek language and alphabet), "
        "regardless of the language they ask the question in or the language of the document.\n\n"
        "You are answering questions about the following document: '{title}'.\n"
        "Use the document content below as your source of truth. "
        "If the answer cannot be found in the text, let the user know in Greek, but try to answer as best as you can.\n\n"
        "Document Content:\n"
        "{content}"
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
            {"title": doc_title, "content": doc_content, "query": query}
        )
        return str(response.content)
    except Exception as e:
        return f"Error interacting with chatbot agent: {str(e)}"
