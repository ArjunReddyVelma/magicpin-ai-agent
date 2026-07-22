from storage.context_store import context_store


class ContextManager:

    def __init__(self):
        self.store = context_store

    def save_context(self, merchant_id, context):
        self.store.save_context(merchant_id, context)

    def get_context(self, merchant_id):
        return self.store.get_context(merchant_id)

    def update_context(self, merchant_id, context):
        self.store.update_context(merchant_id, context)

    def delete_context(self, merchant_id):
        self.store.delete_context(merchant_id)