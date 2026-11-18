from pathlib import Path

from nlp_content_policy_appeals.desk_cli import load_case


def test_overturned_finding_is_not_a_completed_lift():
    fixture = Path(__file__).parents[1] / 'fixtures'
    output = load_case(fixture / 'work.json', fixture / 'business.json')
    assert output[0]['verdict'] == '撤销'
    assert output[0]['action'] == '等待执行确认'
    assert output[1]['action'] == '维持已确认限制'
