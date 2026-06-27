from core.utils import now


def log(task, action, details=None):
    task.setdefault("history", []).append({
        "action": action,
        "time": now().isoformat(),
        "details": details or {},
    })
