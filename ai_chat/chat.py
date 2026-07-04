import json
from typing import Any, Dict

from ai_chat.answer_builder import build_answer
from ai_chat.executor import execute_tool_call
from ai_chat.router import route


def chat(question: str) -> Dict[str, Any]:
    tool_call = route(question)
    execution_result = execute_tool_call(tool_call)
    answer = build_answer(question=question, execution_result=execution_result)

    return {
        "question": question,
        "tool_call": tool_call,
        "execution_result": execution_result,
        "answer": answer,
    }


if __name__ == "__main__":
    print("AI Analytics CLI")
    print("Type your question and press Enter.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            question = input("You: ").strip()
        except KeyboardInterrupt:
            print("\nBye.")
            break

        if not question:
            continue

        if question.lower() in {"exit", "quit", "q"}:
            print("Bye.")
            break

        try:
            output = chat(question)

            print("\nTOOL CALL:")
            print(json.dumps(output["tool_call"], ensure_ascii=False, indent=2))

            print("\nANSWER:")
            print(output["answer"])
            print()

        except Exception as exc:
            print(f"\nERROR: {exc}\n")