"""Per-user lock for long Gemini jobs (workout), separate from VEO lock."""


class TaskManager:
    def __init__(self):
        self._busy: set[int] = set()

    def is_busy(self, user_id: int) -> bool:
        return user_id in self._busy

    def acquire(self, user_id: int) -> None:
        self._busy.add(user_id)

    def release(self, user_id: int) -> None:
        self._busy.discard(user_id)

    async def run(self, user_id: int, _name: str) -> None:
        self.acquire(user_id)


task_manager = TaskManager()
