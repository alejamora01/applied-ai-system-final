from retriever import Retriever, tokenize

r = Retriever()


def test_knowledge_base_loaded():
    assert len(r.chunks) >= 10


def test_tokenize_drops_stopwords_and_stems():
    assert "the" not in tokenize("the walking")
    assert "walk" in tokenize("walking")


def test_hot_weather_query_finds_walking_section():
    hit = r.search("walk in hot weather", k=1)[0]
    assert hit.chunk.source == "walking.md"
    assert hit.chunk.title == "Hot weather"


def test_human_medicine_query_finds_warning():
    hit = r.search("can I give my dog ibuprofen", k=1)[0]
    assert hit.chunk.title == "Never give human medicine"


def test_category_filter_prefers_category():
    hits = r.search("brush", k=3, category="grooming")
    assert hits and hits[0].chunk.category == "grooming"


def test_nonsense_query_returns_nothing():
    assert r.search("qwertyuiop zzzz") == []


def test_empty_query_returns_nothing():
    assert r.search("") == []


def test_scores_are_between_zero_and_one():
    for hit in r.search("feed puppy meals", k=5):
        assert 0 < hit.score <= 1
