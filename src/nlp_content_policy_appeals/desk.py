"""申诉裁决与限制执行核对。

两层结构：
1. AppealAdjudication 逐条认定核对——发言日适用的政策版本、初判证据原文、
   归属还原与适用性是否分开解决，产出维持/撤销/待核及具体待核点。
2. RestrictionDesk 按限制汇总——一项限制可由多项独立认定共同支撑，部分
   改判后只按仍成立认定支持的更窄范围调整；调整是否实际生效以对应回执为准，
   旧回执只能证明初次限制，不能证明较晚的调整已执行。
"""
from datetime import date

from .context import Conversation

# 作用范围宽到窄：账号 > 帖子
SCOPE_RANK = {'account': 2, 'post': 1}
SCOPE_LABEL = {'account': '账号作用范围', 'post': '帖子作用范围'}


def _basis_findings(limit):
    value = limit.get('basis')
    if value is None:
        value = [limit['finding']]
    return value if isinstance(value, list) else [value]


class ApplicablePolicy:
    def __init__(self, editions):
        self.editions = {entry['id']: date.fromisoformat(entry['effective']) for entry in editions}
        self.texts = {entry['id']: entry for entry in editions}

    def edition_on(self, happened):
        latest = max((until for until in self.editions.values() if until <= happened), default=None)
        for policy_id, effective in self.editions.items():
            if effective == latest:
                return policy_id
        return None

    def covers(self, finding, carried_policy):
        happened = date.fromisoformat(finding['date'])
        return self.edition_on(happened) == carried_policy

    def clause(self, policy_id, clause_id):
        for clause in self.texts.get(policy_id, {}).get('clauses', []):
            if clause['id'] == clause_id:
                return clause
        return None


class AppealAdjudication:
    def __init__(self, policies, findings, conversation=None):
        self.policies = policies
        self.findings = {item['id']: item for item in findings}
        self.conversation = conversation

    def verdict(self, review):
        finding = self.findings[review['finding']]
        happened = date.fromisoformat(review['date'])
        applicable_edition = self.policies.edition_on(happened)
        carried = finding['policy']

        pending = list(review.get('pending_points', []))

        # 1. 帖子归属一致性：审核记录必须对准初判认定的内容
        if finding['post'] != review['post']:
            pending.append(f"审核对象 {review['post']} 与认定帖子 {finding['post']} 不一致")

        # 2. 版本适用：发言时生效的条款才可用
        if applicable_edition != carried:
            pending.append(
                f'发言日 {review["date"]} 适用 {applicable_edition}，初判引用的是 {carried}，需改按当时生效版本'
            )

        # 3. 归属结论与完整线程交叉核对
        attribution = review.get('attribution')
        attribution_ok = False
        note = '无线程可核对'
        if self.conversation is not None:
            attribution_ok, note = self.conversation.verify(finding['post'], attribution)
            if not attribution_ok:
                pending.append(f'归属核对未通过：{note}')
        elif not review.get('attribution_resolved'):
            pending.append('归属尚未还原：原作者、引文边界、答复对象待补')

        # 4. 归属已解决但适用性未解决——必须留下具体待核点
        if review.get('attribution_resolved') and review.get('applicable') is None and not pending:
            pending.append('归属已还原，但防护规则是否覆盖该行为尚未认定')

        # 5. 机器侧条款覆盖检查（审核员明确给出适用性结论时校验）
        clause = self.policies.clause(carried, finding.get('clause'))
        if clause is not None and review.get('applicable') is True and finding.get('behavior') not in clause['covers']:
            pending.append(
                f"{finding['clause']} 的覆盖范围 {clause['covers']} 不含认定行为 {finding['behavior']}"
            )

        if pending:
            decision = '待核'
        elif review['verified'] is False or review.get('applicable') is False:
            decision = '撤销'
        else:
            decision = '维持'

        return {
            'finding': finding['id'],
            'post': finding['post'],
            'decision': decision,
            'carried_policy': carried,
            'applicable_edition_on_post_date': applicable_edition,
            'clause': finding.get('clause'),
            'behavior': finding.get('behavior'),
            'evidence': list(finding.get('evidence', [])),
            'attribution': attribution,
            'attribution_cross_check': note if self.conversation is not None else '无线程可核对',
            'applicable': review.get('applicable'),
            'pending_points': pending,
            'claimed_scope': finding.get('scope'),
            'reason': review.get('reason', ''),
        }


class RestrictionDesk:
    def __init__(self, restrictions, receipts):
        self.restrictions = restrictions
        self.receipts = receipts

    def _receipts_for(self, limit_id):
        return [item for item in self.receipts if item['limit'] == limit_id]

    def _latest(self, limit_id):
        rows = self._receipts_for(limit_id)
        return rows[-1] if rows else None

    def _adjusted_scope(self, surviving_findings, finding_map):
        if not surviving_findings:
            return None
        return min(
            (finding_map[fid].get('scope', 'post') for fid in surviving_findings),
            key=lambda scope: SCOPE_RANK.get(scope, 0),
        )

    def what_next(self, adjudications):
        decisions = {row['finding']: row for row in adjudications}
        rows = []
        for restriction in self.restrictions:
            basis = _basis_findings(restriction)
            overturned, surviving, held_pending = [], [], []
            for fid in basis:
                decision = decisions.get(fid)
                if decision is None:
                    held_pending.append(fid)
                elif decision['decision'] == '撤销':
                    overturned.append(fid)
                elif decision['decision'] == '待核':
                    held_pending.append(fid)
                else:
                    surviving.append(fid)

            finding_map = {fid: decisions.get(fid, {}) for fid in basis}
            original_scope = restriction.get('scope')
            adjusted_scope = self._adjusted_scope(surviving, {
                fid: {'scope': decisions[fid]['claimed_scope']} for fid in surviving
            }) if surviving else None

            if not surviving and not held_pending:
                outcome = '全部撤销-应解除'
            elif not surviving and held_pending:
                outcome = '依据全部待核-挂起'
            elif overturned and surviving:
                outcome = '部分维持-应收窄'
            elif surviving and held_pending:
                outcome = '部分维持-含待核'
            elif surviving:
                outcome = '全部维持'
            else:
                outcome = '等待认定'

            latest = self._latest(restriction['id'])
            ack_status = latest['status'] if latest else None
            ack_for = latest['issued_for'] if latest else None
            withdrawn = latest.get('withdrawn_scope') if latest else None

            # 该撤回的范围（人工结论）与已撤回范围（执行回执）分开列示
            if outcome == '全部撤销-应解除':
                required_withdrawal = original_scope
            elif outcome in ('部分维持-应收窄', '部分维持-含待核'):
                required_withdrawal = original_scope if SCOPE_RANK.get(adjusted_scope, 0) < SCOPE_RANK.get(original_scope, 0) else None
            else:
                required_withdrawal = None

            if outcome == '全部撤销-应解除':
                if ack_for != 'lift' or ack_status in (None, 'processing'):
                    action = '等待解除回执'
                elif ack_status == 'rejected':
                    action = '解除被拒-重新发出'
                elif ack_status == 'complete' and withdrawn == original_scope:
                    action = '解除已生效'
                else:
                    action = '核对解除范围'
            elif outcome in ('部分维持-应收窄', '部分维持-含待核'):
                if ack_for != 'adjust' or ack_status in (None, 'processing'):
                    action = '等待收窄回执'
                elif ack_status == 'rejected':
                    action = '收窄被拒-重新发出'
                elif ack_status == 'complete' and withdrawn == original_scope:
                    action = '收窄已生效'
                else:
                    action = '核对收窄范围'
            elif outcome == '全部维持':
                action = '维持已确认限制' if ack_status == 'complete' and ack_for == 'initial' else '等待执行确认'
            else:
                action = '等待认定'

            rows.append({
                'limit': restriction['id'],
                'measure': restriction.get('measure'),
                'original_scope': original_scope,
                'basis': basis,
                'overturned_findings': overturned,
                'surviving_findings': surviving,
                'pending_findings': held_pending,
                'outcome': outcome,
                'adjusted_scope': adjusted_scope,
                'required_withdrawal_scope': required_withdrawal,
                'latest_receipt': {'issued_for': ack_for, 'status': ack_status, 'withdrawn_scope': withdrawn},
                'withdrawn_confirmed': withdrawn,
                'action': action,
                'all_receipts': [
                    {'issued_for': item['issued_for'], 'status': item['status'], 'withdrawn_scope': item.get('withdrawn_scope')}
                    for item in self._receipts_for(restriction['id'])
                ],
                'pending_points': [
                    point for fid in held_pending for point in decisions.get(fid, {}).get('pending_points', [])
                ],
            })
        return rows


def assess(case, registry, threads=None):
    conversation = Conversation(threads) if threads else None
    review = AppealAdjudication(
        ApplicablePolicy(registry['policies']), registry['findings'], conversation
    )
    adjudications = [review.verdict(item) for item in case['reviews']]
    desk = RestrictionDesk(registry['limits'], registry['receipts']).what_next(adjudications)
    return {'findings': adjudications, 'limits': desk}
