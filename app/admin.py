"""Админка для редактирования содержимого ad/tip-блока.

Защищена HTTP Basic Auth через переменные окружения
ADMIN_USER и ADMIN_PASSWORD (задаются в systemd-юните в проде).
"""
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app import ads, db

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()
security = HTTPBasic()


def require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    """Проверяет HTTP Basic Auth против переменных окружения.

    Используем secrets.compare_digest, чтобы не дать атакующему
    угадывать пароль по времени ответа (timing attack).
    """
    expected_user = os.getenv("ADMIN_USER", "admin")
    expected_pass = os.getenv("ADMIN_PASSWORD", "change-me")
    user_ok = secrets.compare_digest(creds.username.encode(), expected_user.encode())
    pass_ok = secrets.compare_digest(creds.password.encode(), expected_pass.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )


@router.get("/admin", response_class=HTMLResponse)
async def admin_form(
    request: Request,
    saved: int = 0,
    _: None = Depends(require_admin),
) -> HTMLResponse:
    """Показывает форму редактирования ad-блока с текущими значениями."""
    current = await ads.get_current()

    # Читаем всю статистику из базы данных
    stats = await db.read_counters()

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "ad": current,
            "saved": bool(saved),
            "stats": stats  # Передаем статистику в шаблон
        },
    )


@router.post("/admin")
async def admin_save(
    label_kind: str = Form(...),
    title: str = Form(...),
    text: str = Form(...),
    button_text: str = Form(...),
    button_url: str = Form(...),
    proxy_url: str = Form(""),
    fallback_text: str = Form(""),
    _: None = Depends(require_admin),
) -> RedirectResponse:
    """Сохраняет новый контент ad-блока и редиректит на GET."""
    # Валидация метки — только два допустимых значения
    if label_kind not in ("ad", "tip"):
        raise HTTPException(status_code=400, detail="invalid label_kind")

    # Обязательные поля не должны быть пустыми
    for name, value in (
        ("title", title),
        ("text", text),
        ("button_text", button_text),
        ("button_url", button_url),
    ):
        if not value.strip():
            raise HTTPException(status_code=400, detail=f"empty {name}")

    await ads.update({
        "label_kind": label_kind,
        "title": title.strip(),
        "text": text.strip(),
        "button_text": button_text.strip(),
        "button_url": button_url.strip(),
        "proxy_url": proxy_url.strip(),
        "fallback_text": fallback_text.strip(),
    })
    # Post-Redirect-Get: избегаем повторного POST при F5
    return RedirectResponse(url="/admin?saved=1", status_code=303)
