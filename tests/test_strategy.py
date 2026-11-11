from app.db.models import KbItem
from app.nlp.strategy import decide

ITEM = KbItem(answer="javob")
RANKED_HIGH = [("Stipendiya", 0.9), ("Boshqa", 0.1)]
RANKED_LOW = [("Stipendiya", 0.4), ("Yotoqxona", 0.3), ("Boshqa", 0.1)]


def found(_query, _category):
    return ITEM, 0.9


def weak(_query, _category):
    return ITEM, 0.1


def nothing(_query, _category):
    return None, 0.0


def run(ranked, retrieve=found, context=None, previous=False, query="uzun savol shu yerda bor"):
    return decide(ranked, query, 0.6, 0.3, context, previous, retrieve)


def test_confident_with_match_answers():
    decision = run(RANKED_HIGH)
    assert decision.kind == "kb"
    assert decision.item is ITEM
    assert decision.category == "Stipendiya"


def test_threshold_is_inclusive():
    assert run([("Stipendiya", 0.6), ("Boshqa", 0.4)]).kind == "kb"


def test_low_confidence_clarifies_with_top_two():
    decision = run(RANKED_LOW)
    assert decision.kind == "clarify"
    assert decision.options == ["Stipendiya", "Yotoqxona"]


def test_second_miss_falls_back():
    assert run(RANKED_LOW, previous=True).kind == "fallback"


def test_weak_similarity_counts_as_miss():
    assert run(RANKED_HIGH, retrieve=weak).kind == "clarify"
    assert run(RANKED_HIGH, retrieve=weak, previous=True).kind == "fallback"


def test_no_item_counts_as_miss():
    assert run(RANKED_HIGH, retrieve=nothing).kind == "clarify"


def test_short_follow_up_uses_context():
    seen = {}

    def spy(query, category):
        seen.update(query=query, category=category)
        return ITEM, 0.9

    decision = run(RANKED_LOW, retrieve=spy, context="Yotoqxona", query="ijtimoiysi-chi?")
    assert decision.kind == "kb"
    assert decision.category == "Yotoqxona"
    assert seen == {"query": "ijtimoiysi?", "category": "Yotoqxona"}


def test_long_question_ignores_context():
    assert run(RANKED_LOW, context="Yotoqxona").kind == "clarify"


def test_confident_short_question_ignores_context():
    assert run(RANKED_HIGH, context="Yotoqxona", query="stipendiya").category == "Stipendiya"
