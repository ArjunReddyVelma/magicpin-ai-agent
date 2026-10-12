class InMemoryEngagementStore:

    def __init__(self):
        self.sent_suppression_keys = set()

    def has_been_sent(self, suppression_key: str) -> bool:
        return suppression_key in self.sent_suppression_keys

    def mark_sent(self, suppression_key: str) -> None:
        self.sent_suppression_keys.add(suppression_key)


engagement_store = InMemoryEngagementStore()