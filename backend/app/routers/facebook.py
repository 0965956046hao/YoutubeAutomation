from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models import FacebookFlowBatchIn, FacebookFlowIn
from app.services import facebook_flow, store
from app.services.facebook_client import FacebookClient

router = APIRouter()


@router.post("/facebook/check")
def check_page() -> dict:
    try:
        with FacebookClient(store.load_config()) as client:
            return client.check_page()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/facebook/flows", status_code=202)
def create_flow(body: FacebookFlowIn) -> dict:
    try:
        return facebook_flow.create_task(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/facebook/flows/batch", status_code=202)
def create_flows_batch(body: FacebookFlowBatchIn) -> dict:
    try:
        page_id = store.load_config().get("facebook_page_id", "")
        return facebook_flow.create_tasks(body.items, page_id=page_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/facebook/flows")
def list_flows() -> dict:
    tasks = facebook_flow.list_tasks()
    uploaded = [t for t in tasks if t.get("status") == "done"]
    active = [t for t in tasks if t.get("status") != "done"]
    return {"tasks": tasks, "active": active, "uploaded": uploaded,
            "active_count": len(active), "uploaded_count": len(uploaded)}


@router.post("/facebook/flows/{task_id}/resume", status_code=202)
def resume_flow(task_id: str) -> dict:
    try:
        return facebook_flow.resume_task(task_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy flow.")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/facebook/flows/{task_id}/retry", status_code=202)
def retry_flow(task_id: str) -> dict:
    """Chạy lại từ đầu flow đang lỗi (tải/cắt/ghép/upload lại toàn bộ)."""
    try:
        return facebook_flow.retry_task(task_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy flow.")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/facebook/flows/{task_id}/cancel", status_code=202)
def cancel_flow(task_id: str) -> dict:
    try:
        return facebook_flow.cancel_task(task_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy flow.")


@router.post("/facebook/flows/{task_id}/thumbnail", status_code=202)
def set_flow_thumbnail(task_id: str) -> dict:
    """Đặt (bù) thumbnail YouTube làm ảnh bìa video Facebook của flow."""
    try:
        return facebook_flow.set_task_thumbnail(task_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy flow.")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/facebook/flows/{task_id}/{name}")
def flow_artifact(task_id: str, name: str) -> FileResponse:
    found = facebook_flow.artifact(task_id, name)
    if not found:
        raise HTTPException(404, "File chưa sẵn sàng.")
    path, filename = found
    return FileResponse(path, filename=filename, media_type="video/mp4" if name == "clip" else "image/jpeg")


@router.delete("/facebook/flows/{task_id}", status_code=202)
def delete_flow(task_id: str) -> dict:
    try:
        result = facebook_flow.delete_task(task_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy flow.")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": result["status"]}
