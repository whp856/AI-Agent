import json

from backend.tools.importer import parse_json_data, parse_csv_data


def test_parse_json():
    data = [{"review_id": "a", "body": "hi", "rating": 4}]
    reviews, note = parse_json_data(json.dumps(data))
    assert len(reviews) == 1
    assert reviews[0].rating == 4
    assert reviews[0].source == "import"


def test_parse_json_missing_id():
    reviews, note = parse_json_data(json.dumps([{"body": "hi", "rating": 4}]))
    assert reviews[0].review_id.startswith("generated:")


def test_parse_json_dict_wrapper():
    data = {"reviews": [{"review_id": "a", "body": "hi", "rating": 4}]}
    reviews, note = parse_json_data(json.dumps(data))
    assert len(reviews) == 1


def test_parse_csv():
    csv_text = "review_id,title,body,rating\n1,t,hello,3\n2,t,world,5\n"
    reviews, note = parse_csv_data(csv_text)
    assert len(reviews) == 2
    assert reviews[1].rating == 5


def test_parse_csv_rating_clamped():
    csv_text = "review_id,body,rating\n1,hi,99\n"
    reviews, note = parse_csv_data(csv_text)
    assert reviews[0].rating == 5
