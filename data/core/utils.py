from datetime import datetime, timedelta


def now():
    return datetime.now()


def parse(dt):
    return datetime.fromisoformat(dt) if dt else None


def fmt_dt(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def cycle_start_end(freq, t):
    if freq == "daily":
        start = datetime(t.year, t.month, t.day)
        end = start + timedelta(days=1)
        label = "daily"
    elif freq == "weekly":
        start_day = t - timedelta(days=t.weekday())
        start = datetime(start_day.year, start_day.month, start_day.day)
        end = start + timedelta(days=7)
        label = "weekly"
    else:
        start = datetime(t.year, t.month, 1)
        if t.month == 12:
            end = datetime(t.year + 1, 1, 1)
        else:
            end = datetime(t.year, t.month + 1, 1)
        label = "monthly"
    return label, start, end


def previous_cycle_bounds(freq, current_start):
    if freq == "daily":
        prev_start = current_start - timedelta(days=1)
        prev_end = current_start
    elif freq == "weekly":
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start
    else:
        prev_end = current_start
        if current_start.month == 1:
            prev_start = datetime(current_start.year - 1, 12, 1)
        else:
            prev_start = datetime(current_start.year, current_start.month - 1, 1)
    return prev_start, prev_end
