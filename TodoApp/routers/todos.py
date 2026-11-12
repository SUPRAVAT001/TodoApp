"""Todo CRUD router for both Jinja2 HTML pages and JSON API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Todos, Users
from ..schemas import TodoRequest, TodoResponse
from ..security import templates, verify_csrf_protection
from .auth import get_current_user, redirect_to_login, require_current_user

router = APIRouter(
    prefix="/todos",
    tags=["todos"],
)


# ═══════════════════════════════════════════════
#  HTML PAGE ROUTES
# ═══════════════════════════════════════════════


@router.get("/add-todo", response_class=HTMLResponse)
async def add_todo_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()
    return templates.TemplateResponse(
        request=request,
        name="add-todo.html",
        context={"request": request, "user": user},
    )


@router.post("/add-todo", response_class=HTMLResponse)
async def add_todo_post(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    priority: int = Form(...),
    complete: str = Form(default="false"),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    verify_csrf_protection(request, csrf_token)

    clean_title = title.strip()
    clean_desc = description.strip()
    is_complete = complete.lower() in ("true", "on", "1")

    if len(clean_title) < 3 or len(clean_title) > 100 or len(clean_desc) < 3 or len(clean_desc) > 300 or not (1 <= priority <= 5):
        return templates.TemplateResponse(
            request=request,
            name="add-todo.html",
            context={
                "request": request,
                "user": user,
                "msg": "Title (3–100 chars), description (3–300 chars), and priority (1–5) are required.",
                "msg_type": "danger",
                "form_data": {
                    "title": clean_title,
                    "description": clean_desc,
                    "priority": priority,
                    "complete": is_complete,
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    new_todo = Todos(
        title=clean_title,
        description=clean_desc,
        priority=priority,
        complete=is_complete,
        owner_id=user.id,
    )
    try:
        db.add(new_todo)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="add-todo.html",
            context={
                "request": request,
                "user": user,
                "msg": "Failed to save todo due to a database error.",
                "msg_type": "danger",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(url="/?msg=Todo+added+successfully&msg_type=success", status_code=status.HTTP_302_FOUND)


@router.get("/edit-todo/{todo_id}", response_class=HTMLResponse)
async def edit_todo_page(
    request: Request,
    todo_id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        return RedirectResponse(url="/?msg=Todo+not+found&msg_type=danger", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="edit-todo.html",
        context={"request": request, "user": user, "todo": todo},
    )


@router.post("/edit-todo/{todo_id}", response_class=HTMLResponse)
async def edit_todo_post(
    request: Request,
    todo_id: int = Path(gt=0),
    title: str = Form(...),
    description: str = Form(...),
    priority: int = Form(...),
    complete: str = Form(default="false"),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    verify_csrf_protection(request, csrf_token)

    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        return RedirectResponse(url="/?msg=Todo+not+found&msg_type=danger", status_code=status.HTTP_302_FOUND)

    clean_title = title.strip()
    clean_desc = description.strip()
    is_complete = complete.lower() in ("true", "on", "1")

    if len(clean_title) < 3 or len(clean_title) > 100 or len(clean_desc) < 3 or len(clean_desc) > 300 or not (1 <= priority <= 5):
        return templates.TemplateResponse(
            request=request,
            name="edit-todo.html",
            context={
                "request": request,
                "user": user,
                "todo": {
                    "id": todo.id,
                    "title": clean_title,
                    "description": clean_desc,
                    "priority": priority,
                    "complete": is_complete,
                },
                "msg": "Title (3–100 chars), description (3–300 chars), and priority (1–5) are required.",
                "msg_type": "danger",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        todo.title = clean_title
        todo.description = clean_desc
        todo.priority = priority
        todo.complete = is_complete
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="edit-todo.html",
            context={
                "request": request,
                "user": user,
                "todo": todo,
                "msg": "Failed to update todo due to a database error.",
                "msg_type": "danger",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(url="/?msg=Todo+updated+successfully&msg_type=success", status_code=status.HTTP_302_FOUND)


@router.post("/delete/{todo_id}")
async def delete_todo(
    request: Request,
    todo_id: int = Path(gt=0),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    verify_csrf_protection(request, csrf_token)

    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        return RedirectResponse(url="/?msg=Todo+not+found&msg_type=danger", status_code=status.HTTP_302_FOUND)

    try:
        db.delete(todo)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(url="/?msg=Could+not+delete+todo&msg_type=danger", status_code=status.HTTP_302_FOUND)

    return RedirectResponse(url="/?msg=Todo+deleted&msg_type=success", status_code=status.HTTP_302_FOUND)


@router.post("/complete/{todo_id}")
async def toggle_complete(
    request: Request,
    todo_id: int = Path(gt=0),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    verify_csrf_protection(request, csrf_token)

    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        return RedirectResponse(url="/?msg=Todo+not+found&msg_type=danger", status_code=status.HTTP_302_FOUND)

    try:
        todo.complete = not todo.complete
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(url="/?msg=Could+not+update+todo+status&msg_type=danger", status_code=status.HTTP_302_FOUND)

    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


# ═══════════════════════════════════════════════
#  JSON / API ROUTES
# ═══════════════════════════════════════════════


@router.get("/api/", response_model=list[TodoResponse], tags=["todos-api"])
async def api_read_all(
    db: Session = Depends(get_db),
    user: Users = Depends(require_current_user),
):
    return (
        db.query(Todos)
        .filter(Todos.owner_id == user.id)
        .order_by(Todos.id.asc())
        .all()
    )


@router.get("/api/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK, tags=["todos-api"])
async def api_read_todo(
    db: Session = Depends(get_db),
    todo_id: int = Path(gt=0),
    user: Users = Depends(require_current_user),
):
    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo {todo_id} not found")
    return todo


@router.post("/api/", response_model=TodoResponse, status_code=status.HTTP_201_CREATED, tags=["todos-api"])
async def api_create_todo(
    todo_request: TodoRequest,
    db: Session = Depends(get_db),
    user: Users = Depends(require_current_user),
):
    todo = Todos(
        title=todo_request.title.strip(),
        description=todo_request.description.strip(),
        priority=todo_request.priority,
        complete=todo_request.complete,
        owner_id=user.id,
    )
    if len(todo.title) < 3 or len(todo.description) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title and description must contain at least 3 non-whitespace characters",
        )
    try:
        db.add(todo)
        db.commit()
        db.refresh(todo)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating todo",
        )
    return todo


@router.put("/api/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_202_ACCEPTED, tags=["todos-api"])
async def api_update_todo(
    todo_request: TodoRequest,
    db: Session = Depends(get_db),
    todo_id: int = Path(gt=0),
    user: Users = Depends(require_current_user),
):
    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo {todo_id} not found")

    clean_title = todo_request.title.strip()
    clean_desc = todo_request.description.strip()
    if len(clean_title) < 3 or len(clean_desc) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title and description must contain at least 3 non-whitespace characters",
        )

    try:
        todo.title = clean_title
        todo.description = clean_desc
        todo.priority = todo_request.priority
        todo.complete = todo_request.complete
        db.commit()
        db.refresh(todo)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while updating todo",
        )
    return todo


@router.delete("/api/{todo_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["todos-api"])
async def api_delete_todo(
    db: Session = Depends(get_db),
    todo_id: int = Path(gt=0),
    user: Users = Depends(require_current_user),
):
    todo = db.query(Todos).filter(Todos.id == todo_id, Todos.owner_id == user.id).first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo {todo_id} not found")
    try:
        db.delete(todo)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while deleting todo",
        )
