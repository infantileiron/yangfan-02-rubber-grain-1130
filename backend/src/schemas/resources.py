from datetime import datetime, timezone


def utc(value: datetime | None):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def dataset_view(dataset, include_rows=False):
    item = {
        "id": dataset.id, "name": dataset.name, "count": len(dataset.rows),
        "checksum": dataset.checksum, "author": dataset.author, "created_at": utc(dataset.created_at),
    }
    if include_rows:
        item["rows"] = dataset.rows
    return item


def run_view(run, include_result=False):
    item = {
        "id": run.id, "dataset_id": run.dataset_id, "label": run.label, "parameter": run.parameter,
        "status": run.status, "error": run.error, "actor": run.actor,
        "created_at": utc(run.created_at), "started_at": utc(run.started_at),
        "finished_at": utc(run.finished_at),
        "calibration_snapshot": run.calibration_snapshot,
    }
    if include_result:
        item["result"] = run.result
    return item


def review_view(review):
    return {
        "id": review.id, "run_id": review.run_id, "decision": review.decision,
        "samples": review.samples, "note": review.note, "reviewer": review.reviewer,
        "created_at": utc(review.created_at),
    }


def calibration_view(item):
    return {
        "id": item.id,
        "dataset_id": item.dataset_id,
        "substrate": item.substrate,
        "status": item.status,
        "chosen_neighbors": item.chosen_neighbors,
        "default_neighbors": item.default_neighbors,
        "blind_master": item.blind_master,
        "blind_samples": item.blind_samples,
        "cv_errors": item.cv_errors,
        "blind_error": item.blind_error,
        "default_blind_error": item.default_blind_error,
        "blind_passed": item.blind_error <= item.default_blind_error,
        "master_count": item.master_count,
        "qualified_count": item.qualified_count,
        "actor": item.actor,
        "publisher": item.publisher,
        "published_at": utc(item.published_at),
        "created_at": utc(item.created_at),
    }


def audit_view(event):
    return {"actor": event.actor, "action": event.action, "subject": event.subject, "created_at": utc(event.created_at)}
