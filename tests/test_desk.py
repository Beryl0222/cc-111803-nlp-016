import json
from pathlib import Path

import pytest

from nlp_content_policy_appeals.context import Conversation
from nlp_content_policy_appeals.desk import AppealAdjudication, ApplicablePolicy, RestrictionDesk, assess
from nlp_content_policy_appeals.desk_cli import load_case

FIXTURE = Path(__file__).parents[1] / 'fixtures'


@pytest.fixture(scope='module')
def result():
    return load_case(FIXTURE / 'work.json', FIXTURE / 'business.json', FIXTURE / 'threads.json')


def _by_id(rows, key, value):
    return next(row for row in rows if row[key] == value)


def test_attribution_recovers_author_quote_and_reply_target():
    threads = json.loads((FIXTURE / 'threads.json').read_text(encoding='utf-8'))
    conversation = Conversation(threads)
    attribution = conversation.attribution('POST-8')
    assert attribution['author'] == 'user-b'
    assert attribution['reply_to'] == 'POST-7'
    assert attribution['is_quoting_another'] is True
    assert attribution['quotes'][0]['source_author'] == 'user-a'
    assert attribution['quotes'][0]['span'] == '你再说一遍'
    # 无引文的直接施压句
    assert conversation.attribution('POST-9')['is_quoting_another'] is False


def test_attribution_cross_check_detects_wrong_author():
    threads = json.loads((FIXTURE / 'threads.json').read_text(encoding='utf-8'))
    conversation = Conversation(threads)
    ok, _ = conversation.verify('POST-8', {
        'original_author': 'user-a',
        'reply_target': 'POST-7',
        'quote_boundary': 'POST-7 中的“你再说一遍”为引文',
    })
    assert ok is True
    ok, note = conversation.verify('POST-8', {
        'original_author': 'user-x',
        'reply_target': 'POST-7',
        'quote_boundary': 'POST-7 中的“你再说一遍”为引文',
    })
    assert ok is False
    assert 'user-a' in note
    # 无引文时 original_author 应对准发帖人本人
    ok, _ = conversation.verify('POST-9', {
        'original_author': 'user-c',
        'reply_target': None,
        'quote_boundary': '无引文标记',
    })
    assert ok is True


def test_f1_quote_and_report_is_overturned_but_lift_not_yet_effective(result):
    finding = _by_id(result['findings'], 'finding', 'F-1')
    assert finding['decision'] == '撤销'
    assert finding['attribution_cross_check'] == '归属结论与完整线程一致'
    limit = _by_id(result['limits'], 'limit', 'L-1')
    assert limit['outcome'] == '全部撤销-应解除'
    # 最新回执是 lift/processing：该撤回不等于已撤回
    assert limit['action'] == '等待解除回执'
    assert limit['required_withdrawal_scope'] == 'post'
    assert limit['withdrawn_confirmed'] is None


def test_policy_edition_must_be_the_one_effective_on_post_date(result):
    finding = _by_id(result['findings'], 'finding', 'F-8')
    assert finding['decision'] == '待核'
    assert finding['carried_policy'] == 'P-5'
    assert finding['applicable_edition_on_post_date'] == 'P-4'
    assert any('P-5' in point and 'P-4' in point for point in finding['pending_points'])
    # 初判证据串中混入了别的案件截图，待核点要具体指出
    assert any('SHOT-8' in point for point in finding['pending_points'])


def test_attribution_resolved_but_applicability_open_keeps_concrete_pending_point(result):
    finding = _by_id(result['findings'], 'finding', 'F-6')
    assert finding['decision'] == '待核'
    assert finding['attribution_cross_check'] == '归属结论与完整线程一致'
    assert finding['pending_points'], '归属解决但适用性未决时必须留下具体待核点'
    assert any('P-4.3' in point for point in finding['pending_points'])


def test_multi_basis_limit_narrows_to_surviving_scope_not_full_restore_or_old_limit(result):
    limit = _by_id(result['limits'], 'limit', 'L-3')
    assert limit['overturned_findings'] == []
    assert set(limit['surviving_findings']) == {'F-4', 'F-5'}
    assert limit['pending_findings'] == ['F-6']
    assert limit['outcome'] == '部分维持-含待核'
    # F-4 是 account、F-5 是 post，最窄只能支持帖子范围
    assert limit['adjusted_scope'] == 'post'
    assert limit['original_scope'] == 'account'
    assert limit['required_withdrawal_scope'] == 'account'


def test_rejected_adjustment_receipt_requires_reissue(result):
    limit = _by_id(result['limits'], 'limit', 'L-3')
    assert limit['latest_receipt'] == {'issued_for': 'adjust', 'status': 'rejected', 'withdrawn_scope': None}
    assert limit['action'] == '收窄被拒-重新发出'
    # 初次回执仍在，但不能证明收窄已执行
    assert {'issued_for': 'initial', 'status': 'complete', 'withdrawn_scope': None} in limit['all_receipts']


def test_completed_lift_receipt_confirms_withdrawn_scope(result):
    limit = _by_id(result['limits'], 'limit', 'L-4')
    assert limit['outcome'] == '全部撤销-应解除'
    assert limit['action'] == '解除已生效'
    assert limit['withdrawn_confirmed'] == 'post'


def test_pending_finding_does_not_block_clear_decisions_on_other_content(result):
    # F-8 待核，但它没有挂在任何限制上；L-1/L-2/L-4 的明确处置照常产出
    actions = {row['limit']: row['action'] for row in result['limits']}
    assert actions['L-2'] == '维持已确认限制'
    assert actions['L-4'] == '解除已生效'
    assert 'L-1' in actions


def test_original_evidence_texts_are_listed_for_review(result):
    finding = _by_id(result['findings'], 'finding', 'F-1')
    assert finding['evidence'] == ['SHOT-8']
    finding2 = _by_id(result['findings'], 'finding', 'F-2')
    assert finding2['evidence'] == ['POST-9']
    assert finding2['decision'] == '维持'


def test_covers_uses_post_date_not_review_date():
    policies = ApplicablePolicy([
        {'id': 'P-4', 'effective': '2026-01-01'},
        {'id': 'P-5', 'effective': '2026-06-01'},
    ])
    assert policies.covers({'date': '2026-05-21'}, 'P-4') is True
    assert policies.covers({'date': '2026-05-21'}, 'P-5') is False
    assert policies.covers({'date': '2026-06-02'}, 'P-5') is True


def test_assess_without_threads_flags_attribution_uncheckable():
    registry = json.loads((FIXTURE / 'business.json').read_text(encoding='utf-8'))
    case = json.loads((FIXTURE / 'work.json').read_text(encoding='utf-8'))
    output = assess(case, registry, threads=None)
    f1 = _by_id(output['findings'], 'finding', 'F-1')
    assert f1['attribution_cross_check'] == '无线程可核对'


def test_stale_initial_receipt_does_not_prove_later_adjustment(result):
    # 构造：只有 initial/complete，没有 adjust 回执时，收窄仍处于等待
    registry = json.loads((FIXTURE / 'business.json').read_text(encoding='utf-8'))
    registry['receipts'] = [r for r in registry['receipts'] if r['issued_for'] == 'initial']
    case = json.loads((FIXTURE / 'work.json').read_text(encoding='utf-8'))
    threads = json.loads((FIXTURE / 'threads.json').read_text(encoding='utf-8'))
    output = assess(case, registry, threads)
    l3 = _by_id(output['limits'], 'limit', 'L-3')
    assert l3['action'] == '等待收窄回执'
    assert l3['withdrawn_confirmed'] is None
