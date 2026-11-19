"""合成对话线程与引文归属核对。

截图只保留单句时，原作者、引文边界和答复对象全部丢失。本模块按完整线程
重建这三项，并对审核员填写的归属结论做交叉核对。
"""


class Conversation:
    def __init__(self, threads):
        self.posts = {post['id']: post for post in threads.get('posts', [])}
        self.shots = {shot['id']: shot for shot in threads.get('screenshots', [])}

    def post(self, post_id):
        return self.posts.get(post_id)

    def screenshot(self, shot_id):
        return self.shots.get(shot_id)

    def attribution(self, post_id):
        """返回机器从完整线程还原的归属四要素。"""
        post = self.posts.get(post_id)
        if post is None:
            return None
        quotes = []
        for quote in post.get('quotes', []):
            source = self.posts.get(quote['post'])
            quotes.append({
                'span': quote['span'],
                'source_post': quote['post'],
                'source_author': quote['author'],
                'source_text': source['text'] if source else None,
            })
        return {
            'post': post_id,
            'author': post['author'],
            'reply_to': post.get('reply_to'),
            'quotes': quotes,
            'is_quoting_another': bool(quotes),
        }

    def verify(self, post_id, review_attribution):
        """把审核员的归属结论与完整线程交叉核对，返回 (是否一致, 说明)。

        original_author 的语义：有引文时指被引原话的作者，无引文时指发帖人本人。
        """
        post = self.posts.get(post_id)
        if post is None:
            return False, f'线程中找不到 {post_id}'
        if not review_attribution:
            return False, '审核记录缺少归属结论'
        problems = []
        machine = self.attribution(post_id)
        expected_author = machine['quotes'][0]['source_author'] if machine['is_quoting_another'] else post['author']
        if review_attribution.get('original_author') != expected_author:
            problems.append(
                f"原作者应为 {expected_author}，记录为 {review_attribution.get('original_author')}"
            )
        if review_attribution.get('reply_target') != post.get('reply_to'):
            problems.append(
                f"答复对象应为 {post.get('reply_to')}，记录为 {review_attribution.get('reply_target')}"
            )
        recorded_has_quote = ('引文' in str(review_attribution.get('quote_boundary', ''))
                              or '引用' in str(review_attribution.get('quote_boundary', '')))
        if machine['is_quoting_another'] and not recorded_has_quote:
            problems.append('线程显示存在引文，但记录未标注引文边界')
        if not machine['is_quoting_another'] and recorded_has_quote and '无引文' not in str(
            review_attribution.get('quote_boundary', '')
        ):
            problems.append('线程显示无引文标记，但记录声称存在引文')
        if problems:
            return False, '；'.join(problems)
        return True, '归属结论与完整线程一致'
