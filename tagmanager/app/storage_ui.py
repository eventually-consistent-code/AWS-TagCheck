"""
Purpose: Storage web app routes — target CRUD, scan trigger, job progress
(htmx-polled), cooperative cancel. Thin handlers over the storage service
layer and job runner; messages ride the query string, errors never 500.
Author(s): John Reed
"""

# FastAPI form handlers declare one parameter per form field — that's the
# framework's signature contract, not call complexity.
# pylint: disable=too-many-arguments,too-many-positional-arguments

import io
import logging
import pathlib
import zipfile

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse

from tagmanager.models.tables import StorageJob, StorageScanRun, StorageTarget
from tagmanager.storage import jobs as storage_jobs
from tagmanager.storage import services
from tagmanager.storage.services import StorageServiceError
from tagmanager.storage.output import write_structure_proposal
from tagmanager.storage.store import latest_complete_run, record_artifact

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
                       age_bands, rollup_owners, rollup_types=None):
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
        "options": {"rollup_owners": bool(rollup_owners),
                    "rollup_types": bool(rollup_types)},
    }


def _zip_dir(path):
    """Zip a directory tree into a BytesIO, relative paths inside."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in sorted(path.rglob("*")):
            if entry.is_file():
                archive.write(entry, entry.relative_to(path))
    buf.seek(0)
    return buf


def storage_ui_router(templates, session_maker, scheduler=None):
    """
    Build the scan-control router (targets, jobs).

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
                       rollup_owners: str = Form(None),
                       rollup_types: str = Form(None)):
        """Create a target from the add form."""
        try:
            fields = _parse_target_form(display_name, backend, account_url,
                                        buckets, prefix, age_bands,
                                        rollup_owners, rollup_types)
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
                      rollup_types: str = Form(None),
                      enabled: str = Form(None)):
        """Apply the edit form."""
        try:
            fields = _parse_target_form(display_name, backend, account_url,
                                        buckets, prefix, age_bands,
                                        rollup_owners, rollup_types)
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


def _generate_artifact(session, run, kind, out_dir):
    """
    Generate one artifact kind for a run; False for unknown kinds.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param kind: lifecycle | tiering | structure | report
    :param out_dir: destination directory
    :returns: True when generated
    :raises StorageServiceError: service-level generation failures
    """
    if kind == "lifecycle":
        services.emit_lifecycle_artifacts(session, run, out_dir)
    elif kind == "tiering":
        services.emit_tiering_artifacts(session, run, out_dir)
    elif kind == "structure":
        result = services.recommend_structure(session, run)
        write_structure_proposal(out_dir, result.recs, result.notes, run)
        record_artifact(session, run, "structure-proposal", out_dir,
                        {"recommendations": len(result.recs)})
    elif kind == "report":
        out_dir.mkdir(parents=True, exist_ok=True)
        services.write_html_report_file(session, run,
                                        out_dir / "storage-report.html")
        record_artifact(session, run, "report", out_dir, {"files": 1})
    else:
        return False
    return True


def storage_insights_router(templates, session_maker, settings=None):
    """
    Insights + artifact routes (cost/savings/recommendations, run pages,
    generate/download).

    :param templates: Jinja2Templates
    :param session_maker: sessionmaker
    :param settings: Settings (artifact_dir; None -> default "artifacts")
    :returns: APIRouter
    """
    router = APIRouter()
    artifact_root = pathlib.Path(
        getattr(settings, "artifact_dir", None) or "artifacts")

    def _latest_run(session, backend):
        return latest_complete_run(session, backend=backend)

    def _insights_context(backend, msg=""):
        """Shared context for the three insights pages."""
        return {"backend": backend, "msg": msg,
                "backends": ["s3", "azure", "gcs", "fs"]}

    def _insights_page(request, backend, msg, template, key, loader):
        """One insights page: latest run + a service-loaded payload."""
        session = session_maker()
        try:
            context = _insights_context(backend, msg)
            run = _latest_run(session, backend)
            context["run"] = run
            if run is not None:
                try:
                    context[key] = loader(session, run)
                except StorageServiceError as err:
                    context["msg"] = str(err)
            return templates.TemplateResponse(request, template, context)
        finally:
            session.close()

    @router.get("/storage/cost")
    def cost_page(request: Request, backend: str = "s3", msg: str = ""):
        """Cost report for the latest run of a backend."""
        return _insights_page(request, backend, msg, "cost.html", "report",
                              services.analyze_cost)

    @router.get("/storage/savings")
    def savings_page(request: Request, backend: str = "s3", msg: str = ""):
        """Per-option savings projections for the latest run."""
        return _insights_page(request, backend, msg, "savings.html",
                              "projections", services.analyze_projections)

    @router.get("/storage/recommendations")
    def recommendations_page(request: Request, backend: str = "s3",
                             msg: str = ""):
        """Structure recommendations for the latest run (persisted)."""
        return _insights_page(request, backend, msg, "recommendations.html",
                              "result", services.recommend_structure)

    @router.get("/storage/runs/{run_id}")
    def run_page(request: Request, run_id: int, msg: str = ""):
        """One run: summary, artifact generation, downloads."""
        session = session_maker()
        try:
            run = session.get(StorageScanRun, run_id)
            if run is None:
                return _redirect("/storage/jobs", "no such run.")
            return templates.TemplateResponse(request, "run.html", {
                "run": run, "msg": msg,
                "artifacts": list(run.artifacts or []),
                "kinds": ["lifecycle", "tiering", "structure", "report"]})
        finally:
            session.close()

    @router.post("/storage/runs/{run_id}/artifacts/{kind}")
    def run_generate_artifact(run_id: int, kind: str):
        """Generate one artifact kind server-side into the artifact dir."""
        out_dir = artifact_root / f"run-{run_id}" / kind
        session = session_maker()
        try:
            run = session.get(StorageScanRun, run_id)
            if run is None:
                return _redirect("/storage/jobs", "no such run.")
            try:
                if not _generate_artifact(session, run, kind, out_dir):
                    return _redirect(f"/storage/runs/{run_id}",
                                     f"unknown artifact kind {kind!r}.")
            except StorageServiceError as err:
                return _redirect(f"/storage/runs/{run_id}", str(err))
        finally:
            session.close()
        return _redirect(f"/storage/runs/{run_id}",
                         f"{kind} artifacts generated.")

    @router.get("/storage/runs/{run_id}/artifacts/{kind}/download")
    def run_download_artifact(run_id: int, kind: str):
        """Zip a recorded artifact directory and stream it down."""
        session = session_maker()
        try:
            run = session.get(StorageScanRun, run_id)
            if run is None:
                return _redirect("/storage/jobs", "no such run.")
            matches = [entry for entry in (run.artifacts or [])
                       if entry.get("kind", "").startswith(kind)]
        finally:
            session.close()
        if not matches:
            return _redirect(f"/storage/runs/{run_id}",
                             f"no {kind} artifacts recorded — generate "
                             "first.")
        directory = pathlib.Path(matches[-1]["dir"])
        if not directory.is_dir():
            return _redirect(f"/storage/runs/{run_id}",
                             f"artifact directory missing on disk: "
                             f"{directory}")
        return StreamingResponse(
            _zip_dir(directory), media_type="application/zip",
            headers={"Content-Disposition":
                     f'attachment; filename="run-{run_id}-{kind}.zip"'})

    return router
