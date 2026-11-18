from datetime import date


class ApplicablePolicy:
    def __init__(self, editions):
        self.editions = {entry['id']: date.fromisoformat(entry['effective']) for entry in editions}

    def covers(self, finding, carried_policy):
        happened = date.fromisoformat(finding['date'])
        latest = max((until for until in self.editions.values() if until <= happened), default=None)
        return latest == self.editions[carried_policy]


class AppealAdjudication:
    def __init__(self, policies, findings):
        self.policies = policies
        self.findings = {item['id']: item for item in findings}

    def verdict(self, review):
        finding = self.findings[review['finding']]
        if finding['post'] != review['post'] or not self.policies.covers(review, finding['policy']):
            return '待核适用规则'
        return '维持' if review['verified'] else '撤销'


class RestrictionDesk:
    def __init__(self, restrictions, acknowledgements):
        self.restrictions = restrictions
        self.acks = {item['limit']: item['status'] for item in acknowledgements}

    def what_next(self, decisions):
        rows = []
        for restriction in self.restrictions:
            key = restriction['id']
            verdict = decisions.get(restriction['finding'])
            acknowledgement = self.acks.get(key)
            if verdict == '撤销':
                action = '等待执行确认' if acknowledgement == 'processing' else '核对解除范围'
            elif verdict == '维持':
                action = '维持已确认限制' if acknowledgement == 'complete' else '等待执行确认'
            else:
                action = '等待认定'
            rows.append({'limit': key, 'verdict': verdict, 'ack': acknowledgement, 'action': action})
        return rows


def assess(case, registry):
    review = AppealAdjudication(ApplicablePolicy(registry['policies']), registry['findings'])
    decisions = {item['finding']: review.verdict(item) for item in case['reviews']}
    return RestrictionDesk(registry['limits'], registry['receipts']).what_next(decisions)
