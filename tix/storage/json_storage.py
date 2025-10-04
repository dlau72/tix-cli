import json
from pathlib import Path
from typing import List, Optional
from tix.models import Task
from tix.storage.history import HistoryManager 


class TaskStorage:
    """JSON-based storage for tasks with context support"""

    def __init__(self, storage_path: Path = None, context: str = None, history: HistoryManager = None):
        """Initialize storage with default or custom path and context"""
        self.context = context or self._get_active_context()
        
        # Use context-specific storage path
        if storage_path:
            self.storage_path = storage_path
        else:
            base_dir = Path.home() / ".tix"
            if self.context == "default":
                self.storage_path = base_dir / "tasks.json"
            else:
                self.storage_path = base_dir / "contexts" / f"{self.context}.json"
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file()

        self.history = history or HistoryManager()

    def _get_active_context(self) -> str:
        """Get the active context from the context file"""
        try:
            active_context_path = Path.home() / ".tix" / "active_context"
            if active_context_path.exists():
                return active_context_path.read_text().strip()
        except:
            pass
        return "default"

    def _ensure_file(self):
        """Ensure storage file exists"""
        if not self.storage_path.exists():
            self._write_data({"next_id": 1, "tasks": []})

    def _read_data(self) -> dict:
        """Read raw data from storage, ensuring backward compatibility"""
        try:
            raw = json.loads(self.storage_path.read_text())

            # --- backward compatibility ---
            if isinstance(raw, list):
                upgraded = []
                max_id = 0
                for i, t in enumerate(raw, start=1):
                    # skip invalid entries
                    if not isinstance(t, dict):
                        continue
                    # ensure valid ID
                    if "id" not in t or not isinstance(t["id"], int) or t["id"] <= 0:
                        t["id"] = i
                    max_id = max(max_id, t["id"])
                    upgraded.append(t)

                upgraded_data = {"next_id": max_id + 1, "tasks": upgraded}
                self._write_data(upgraded_data)
                return upgraded_data

            # new format (dict with tasks + next_id)
            if isinstance(raw, dict) and "tasks" in raw and "next_id" in raw:
                return raw

        except (json.JSONDecodeError, FileNotFoundError):
            pass

        # fallback if corrupt or missing
        return {"next_id": 1, "tasks": []}

    def _write_data(self, data: dict):
        self.storage_path.write_text(json.dumps(data, indent=2))

    def load_tasks(self) -> List[Task]:
        """Load all tasks from storage"""
        data = self._read_data()
        return [Task.from_dict(item) for item in data["tasks"]]

    def save_tasks(self, tasks: List[Task]):
        """Save all tasks to storage"""
        data = self._read_data()
        data["tasks"] = [task.to_dict() for task in tasks]
        self._write_data(data)

    def add_task(self, text: str, priority: str = 'medium', tags: List[str] = None, due:str=None, is_global: bool = False, record_history: bool = True) -> Task:
        """Add a new task and return it"""
        data = self._read_data()
        new_id = data["next_id"]
        new_task = Task(id=new_id, text=text, priority=priority, tags=tags or [])
        data["tasks"].append(new_task.to_dict())
        data["next_id"] = new_id + 1
        self._write_data(data)

        if record_history:
            self.history.record({
                "op": "add",
                "after": new_task.to_dict()
            })
        return new_task

    def get_task(self, task_id: int) -> Optional[Task]:
        """Get a specific task by ID"""
        tasks = self.load_tasks()
        for task in tasks:
            if task.id == task_id:
                return task
        return None

    def update_task(self, task: Task, record_history: bool = True):
        """Update an existing task"""
        tasks = self.load_tasks()
        for i, t in enumerate(tasks):
            if t.id == task.id:
                old_task = t
                tasks[i] = task
                self.save_tasks(tasks)

                if record_history:
                    self.history.record({
                        "op": "update",
                        "before": old_task.to_dict(),
                        "after": task.to_dict()
                    })
                return

    def delete_task(self, task_id: int, record_history: bool = True) -> bool:
        """Delete a task by ID, return True if deleted"""
        tasks = self.load_tasks()
        original_count = len(tasks)
        new_tasks = [t for t in tasks if t.id != task_id]
        if len(new_tasks) < original_count:
            old_task = next(t for t in tasks if t.id ==task_id)
            self.save_tasks(new_tasks)

            if record_history:
                self.history.record({
                    "op": "delete",
                    "before": old_task.to_dict()
                })
            return True
        return False

    def get_active_tasks(self) -> List[Task]:
        """Get all incomplete tasks"""
        return [t for t in self.load_tasks() if not t.completed]

    def get_completed_tasks(self) -> List[Task]:
        """Get all completed tasks"""
        return [t for t in self.load_tasks() if t.completed]
    
    def get_attachment_dir(self, task_id: int) -> Path:
        """Return the path where attachments for a task should be stored"""
        return Path.home() / ".tix" / "attachments" / str(task_id)
