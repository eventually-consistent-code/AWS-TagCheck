"""
Purpose: Storage web app routes — target CRUD, scan trigger, job progress
(htmx-polled), cooperative cancel. Thin handlers over the storage service
layer and job runner; messages ride the query string, errors never 500.
Author(s): John Reed
"""

# FastAPI form handlers declare one parameter per form field — that's the
# framework's signature contract, not call complexity.
# pylint: disable=too-many-arguments,too-many-positional-arguments

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from tagmanager.models.tables import StorageJob, StorageTarget
from tagmanager.storage import jobs as storage_jobs
from tagmanager.storage.services import StorageServiceError

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.storage_ui")
LOG.setLevel(logging.INFO)

TERMINAL_STATES = ("done", "failed", "cancelled", "interrupted")


def _redirect(url, msg=""):
    """303 redirect with an optional query-string message."""
    if msg:
        from urllib.parse import quote  # pylint: disable=import-outside-toplevel
        url = f"{url}?msg={quote(msg)}"
    return RedirectResponse(url, status_code=303)


def _parse_target_form(display_name, backend, account_url, buckets, prefix,
                       age_bands, rollup_owners):
    """
    Form fields -> StorageTarget column values.

    :returns: dict of column values
    :raises ValueError: unparseable age bands
    """
    bands = []
    if age_bands.strip():
        bands = sorted(int(part) for part in age_bands.split(","))
    return {
        "display_name": display_name.strip(),
        "backend": backend,
        "account_url": account_url.strip(),
        "buckets": [b.strip() for b in buckets.splitlines() if b.strip()],
        "prefix": prefix.strip(),
        "age_band_days": bands,
        "options": {"rollup_owners": bool(rollup_owners)},
    }


def storage_ui_router(templates, session_maker, scheduler=None):
    """
    Build the storage web-app router.

    :param templates: Jinja2Templates
    :param session_maker: sessionmaker
    :param scheduler: APScheduler instance (None disables scan triggers)
    :returns: APIRouter
    """
    router = APIRouter()

    @router.get("/storage/targets")
    def targets_page(request: Request, msg: str = ""):
        """List targets + the add form."""
        session = session_maker()
        try:
            rows = session.query(StorageTarget).order_by(StorageTarget.id).all()
            return templates.TemplateResponse(request, "targets.html",
                                              {"rows": rows, "msg": msg})
        finally:
            session.close()

    @router.post("/storage/targets")
    def targets_create(display_name: str = Form(""), backend: str = Form("s3"),
                       account_url: str = Form(""), buckets: str = Form(""),
                       prefix: str = Form(""), age_bands: str = Form(""),
                       rollup_owners: str = Form(None)):
        """Create a target from the add form."""
        try:
            fields = _parse_target_form(display_name, backend, account_url,
                                        buckets, prefix, age_bands,
                                        rollup_owners)
        except ValueError:
            return _redirect("/storage/targets",
                             "bad age bands — expected e.g. 90,365")
        session = session_maker()
        try:
            session.add(StorageTarget(**fields))
            session.commit()
        finally:
            session.close()
        return _redirect("/storage/targets", "target added.")

    @router.get("/storage/targets/{target_id}/edit")
    def target_edit_page(request: Request, target_id: int, msg: str = ""):
        """Edit form for one target."""
        session = session_maker()
        try:
            row = session.get(StorageTarget, target_id)
            if row is None:
                return _redirect("/storage/targets", "no such target.")
            return templates.TemplateResponse(request, "target_edit.html",
                                              {"row": row, "msg": msg})
        finally:
            session.close()

    @router.post("/storage/targets/{target_id}")
    def target_update(target_id: int, display_name: str = Form(""),
                      backend: str = Form("s3"), account_url: str = Form(""),
                      buckets: str = Form(""), prefix: str = Form(""),
                      age_bands: str = Form(""),
                      rollup_owners: str = Form(None),
                      enabled: str = Form(None)):
        """Apply the edit form."""
        try:
            fields = _parse_target_form(display_name, backend, account_url,
                                        buckets, prefix, age_bands,
                                        rollup_owners)
        except ValueError:
            return _redirect(f"/storage/targets/{target_id}/edit",
                             "bad age bands — expected e.g. 90,365")
        session = session_maker()
        try:
            row = session.get(StorageTarget, target_id)
            if row is None:
                return _redirect("/storage/targets", "no such target.")
            for key, value in fields.items():
                setattr(row, key, value)
            row.enabled = bool(enabled)
            session.commit()
        finally:
            session.close()
        return _redirect("/storage/targets", "target updated.")

    @router.post("/storage/targets/{target_id}/scan")
    def target_scan(target_id: int):
        """Kick off a background scan job for a target."""
        if scheduler is None:
            return _redirect("/storage/targets",
                             "no scheduler in this deployment — scans run "
                             "from the CLI here.")
        try:
            job_id = storage_jobs.submit_scan(scheduler, session_maker,
                                              target_id)
        except StorageServiceError as err:
            return _redirect("/storage/targets", str(err))
        return _redirect("/storage/jobs", f"scan started (job {job_id}).")

    @router.get("/storage/jobs")
    def jobs_page(request: Request, msg: str = ""):
        """Job list, newest first; active rows poll their progress."""
        session = session_maker()
        try:
            rows = (session.query(StorageJob, StorageTarget)
                    .join(StorageTarget,
                          StorageJob.target_id == StorageTarget.id)
                    .order_by(StorageJob.id.desc()).limit(50).all())
            return templates.TemplateResponse(
                request, "jobs.html",
                {"rows": rows, "msg": msg,
                 "terminal_states": TERMINAL_STATES})
        finally:
            session.close()

    @router.get("/storage/jobs/{job_id}/progress")
    def job_progress(request: Request, job_id: int):
        """htmx-polled fragment; terminal states fire the done trigger."""
        session = session_maker()
        job = session.get(StorageJob, job_id)
        finished = job is None or job.state in TERMINAL_STATES
        response = templates.TemplateResponse(
            request, "_job_progress.html", {"job": job},
            headers={"HX-Trigger": "done"} if finished else {})
        session.close()
        return response

    @router.post("/storage/jobs/{job_id}/cancel")
    def job_cancel(job_id: int):
        """Cooperative cancel — honored at the next flush boundary."""
        if storage_jobs.request_cancel(session_maker, job_id):
            return _redirect("/storage/jobs",
                             f"job {job_id}: cancelling at the next batch "
                             "boundary.")
        return _redirect("/storage/jobs",
                         f"job {job_id} is not active — nothing to cancel.")

    return router
