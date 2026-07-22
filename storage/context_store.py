class InMemoryContextStore:

    def __init__(self):
        self.contexts = {}

    def save_context(self, merchant_id, context):
        self.contexts[merchant_id] = context

    def get_context(self, merchant_id):
        return self.contexts.get(merchant_id)

    def update_context(self, merchant_id, new_context):
        if merchant_id not in self.contexts:
            self.contexts[merchant_id] = {}

        self.contexts[merchant_id].update(new_context)

    def delete_context(self, merchant_id):
        self.contexts.pop(merchant_id, None)

# Shared singleton instance
context_store = InMemoryContextStore()