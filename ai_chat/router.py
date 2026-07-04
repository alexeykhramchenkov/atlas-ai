import json

from ai_chat.routing.route import route


if __name__ == "__main__":
    test_questions = [
        "Сколько заказов всего?",
        "Какая сумма заказов за последние 45 дней?",
        "Сколько отмен было?",
        "Какой процент отмен?",
        "Какой средний чек?",
        "Покажи общие заказы и выручку",
        "What is total revenue?",
        "How many total orders?",
        "What is average order value?",
        "112",
    ]

    for question in test_questions:
        print("\nQUESTION:", question)
        print(json.dumps(route(question), ensure_ascii=False, indent=2))
