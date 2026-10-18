from datetime import datetime, time

from pydantic import BaseModel

from app.models import AssignmentTarget, Frequency
from app.services.tasks import PatientTask, TaskState


class TaskOut(BaseModel):
    """Egy előírás aktuális időszaka a beteg szemszögéből (számított, nem tárolt)."""

    kind: AssignmentTarget
    code: str
    name: str
    frequency: Frequency
    interval_days: int | None
    due_time: time
    period_start: datetime
    period_end: datetime
    due_at: datetime
    state: TaskState
    done_at: datetime | None
    previous_missed: bool
    catch_up_until: datetime | None
    catch_up_suggested_at: datetime | None


def task_out(task: PatientTask) -> TaskOut:
    a = task.assignment
    return TaskOut(
        kind=a.target_kind,
        code=task.code,
        name=task.name,
        frequency=a.frequency,
        interval_days=a.interval_days,
        due_time=a.due_time,
        period_start=task.period_start,
        period_end=task.period_end,
        due_at=task.due_at,
        state=task.state,
        done_at=task.done_at,
        previous_missed=task.previous_missed,
        catch_up_until=task.catch_up_until,
        catch_up_suggested_at=task.catch_up_suggested_at,
    )
