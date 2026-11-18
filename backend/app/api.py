from datetime import datetime, time, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app import security
from app.models import ClickEvent, URL, User, utcnow
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, URLCreate, URLListResponse, URLPatch, URLResponse, UserResponse

router = APIRouter(prefix="/api/v1")
redirect_router = APIRouter()
bearer = HTTPBearer(auto_error=False)


async def get_session(request: Request):
    async with request.app.state.session_factory() as session:
        yield session


async def get_current_user(request: Request,
                           credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                           session=Depends(get_session)) -> User:
    unauthorized = HTTPException(401, "Your session has expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = security.decode_access_token(credentials.credentials, request.app.state.settings)
        user_id = str(UUID(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise unauthorized
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def link_response(link: URL, settings) -> URLResponse:
    return URLResponse(id=link.id, original_url=link.original_url, short_code=link.short_code,
                       short_url=f"{settings.public_base_url}/r/{link.short_code}", title=link.title,
                       is_active=link.is_active, created_at=link.created_at, expires_at=link.expires_at,
                       click_count=link.click_count)


async def owned_link(session, url_id: UUID, user_id: str) -> URL:
    link = await session.scalar(select(URL).where(URL.id == str(url_id), URL.user_id == user_id, URL.deleted_at.is_(None)))
    if link is None:
        raise HTTPException(404, "Link not found")
    return link


async def auth_limit(request: Request):
    identity = request.client.host if request.client else "unknown"
    await request.app.state.limiter.check("auth", identity, request.app.state.settings.auth_rate_limit, 60)


@router.post("/auth/register", response_model=UserResponse, status_code=201, tags=["Authentication"])
async def register(body: RegisterRequest, request: Request, session=Depends(get_session)):
    await auth_limit(request)
    hashed = await run_in_threadpool(security.hash_password, body.password)
    user = User(email=body.email, name=body.name, password_hash=hashed)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "An account with this email already exists")
    return user


@router.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(body: LoginRequest, request: Request, session=Depends(get_session)):
    await auth_limit(request)
    user = await session.scalar(select(User).where(User.email == body.email))
    valid = await run_in_threadpool(security.verify_password, body.password, user.password_hash if user else security.dummy_hash)
    if user is None or not valid:
        raise HTTPException(401, "Email or password is incorrect", headers={"WWW-Authenticate": "Bearer"})
    settings = request.app.state.settings
    return TokenResponse(access_token=security.create_access_token(user.id, settings),
                         expires_in=settings.access_token_expire_minutes * 60, user=UserResponse.model_validate(user))


@router.get("/auth/me", response_model=UserResponse, tags=["Authentication"])
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/urls", response_model=URLResponse, status_code=201, tags=["Links"])
async def create_url(body: URLCreate, request: Request, user: User = Depends(get_current_user), session=Depends(get_session)):
    settings = request.app.state.settings
    await request.app.state.limiter.check("create", user.id, settings.create_rate_limit, 3600)
    user_id = user.id  # preserve before a rollback expires the loaded user
    for _ in range(10):
        code = body.custom_alias if body.custom_alias else security.generate_short_code()
        link = URL(user_id=user_id, original_url=body.original_url, short_code=code,
                   title=body.title.strip(), expires_at=body.expires_at)
        session.add(link)
        try:
            await session.commit()
            return link_response(link, settings)
        except IntegrityError as exc:
            await session.rollback()
            # Only alias uniqueness is retryable; do not hide other database errors.
            if "short_code" not in str(exc.orig):
                raise
            if body.custom_alias:
                raise HTTPException(409, "This alias is already taken. Choose another.")
    raise HTTPException(503, "Unable to allocate a short code. Please retry.")


@router.get("/urls", response_model=URLListResponse, tags=["Links"])
async def list_urls(request: Request, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
                    search: str = Query("", max_length=160),
                    status: Literal["all", "active", "inactive", "expired"] = "all",
                    user: User = Depends(get_current_user), session=Depends(get_session)):
    conditions = [URL.user_id == user.id, URL.deleted_at.is_(None)]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        conditions.append(or_(URL.title.ilike(pattern, escape="\\"), URL.original_url.ilike(pattern, escape="\\"), URL.short_code.ilike(pattern, escape="\\")))
    now = utcnow()
    if status == "active":
        conditions.extend([URL.is_active.is_(True), or_(URL.expires_at.is_(None), URL.expires_at > now)])
    elif status == "inactive":
        conditions.extend([URL.is_active.is_(False), or_(URL.expires_at.is_(None), URL.expires_at > now)])
    elif status == "expired":
        conditions.append(URL.expires_at <= now)
    total = await session.scalar(select(func.count()).select_from(URL).where(*conditions))
    items = (await session.scalars(select(URL).where(*conditions).order_by(URL.created_at.desc(), URL.id.desc())
                                   .offset((page - 1) * page_size).limit(page_size))).all()
    return URLListResponse(items=[link_response(item, request.app.state.settings) for item in items],
                           total=total, page=page, page_size=page_size)


@router.get("/urls/{url_id}", response_model=URLResponse, tags=["Links"])
async def get_url(url_id: UUID, request: Request, user: User = Depends(get_current_user), session=Depends(get_session)):
    return link_response(await owned_link(session, url_id, user.id), request.app.state.settings)


@router.patch("/urls/{url_id}", response_model=URLResponse, tags=["Links"])
async def patch_url(url_id: UUID, body: URLPatch, request: Request, user: User = Depends(get_current_user), session=Depends(get_session)):
    await request.app.state.limiter.check("manage", user.id, 300, 60)
    link = await owned_link(session, url_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Provide at least one field to update")
    for key, value in changes.items():
        setattr(link, key, value.strip() if key == "title" else value)
    await session.commit()
    await request.app.state.cache.invalidate(link.short_code)
    return link_response(link, request.app.state.settings)


@router.delete("/urls/{url_id}", status_code=204, tags=["Links"])
async def delete_url(url_id: UUID, request: Request, user: User = Depends(get_current_user), session=Depends(get_session)):
    await request.app.state.limiter.check("manage", user.id, 300, 60)
    link = await owned_link(session, url_id, user.id)
    link.deleted_at = utcnow()
    link.is_active = False
    await session.commit()
    await request.app.state.cache.invalidate(link.short_code)
    return Response(status_code=204)


def period_start(days: int) -> datetime:
    if days not in {7, 30, 90}:
        raise HTTPException(422, "days must be 7, 30 or 90")
    today = utcnow().date()
    return datetime.combine(today - timedelta(days=days - 1), time.min, tzinfo=timezone.utc)


async def daily_series(session, conditions, start: datetime, days: int):
    date = func.date(ClickEvent.clicked_at)
    results = (await session.execute(select(date, func.count()).where(*conditions, ClickEvent.clicked_at >= start)
                                     .group_by(date).order_by(date))).all()
    counts = {str(day)[:10]: count for day, count in results}
    return [{"date": (start.date() + timedelta(days=i)).isoformat(),
             "clicks": counts.get((start.date() + timedelta(days=i)).isoformat(), 0)} for i in range(days)]


@router.get("/urls/{url_id}/analytics", tags=["Analytics"])
async def url_analytics(url_id: UUID, days: int = Query(30), user: User = Depends(get_current_user), session=Depends(get_session)):
    start = period_start(days)
    link = await owned_link(session, url_id, user.id)
    conditions = [ClickEvent.url_id == link.id]
    series = await daily_series(session, conditions, start, days)
    refs = (await session.execute(select(ClickEvent.referrer, func.count()).where(*conditions, ClickEvent.clicked_at >= start)
                                  .group_by(ClickEvent.referrer).order_by(func.count().desc(), ClickEvent.referrer).limit(10))).all()
    devices = (await session.execute(select(ClickEvent.device, func.count()).where(*conditions, ClickEvent.clicked_at >= start)
                                     .group_by(ClickEvent.device).order_by(func.count().desc(), ClickEvent.device))).all()
    return {"url_id": link.id, "short_code": link.short_code, "total_clicks": link.click_count,
            "period_clicks": sum(row["clicks"] for row in series), "days": days, "clicks_by_day": series,
            "referrers": [{"referrer": key, "clicks": value} for key, value in refs],
            "devices": [{"device": key, "clicks": value} for key, value in devices]}


@router.get("/dashboard", tags=["Analytics"])
async def dashboard(request: Request, days: int = Query(30), user: User = Depends(get_current_user), session=Depends(get_session)):
    start, now = period_start(days), utcnow()
    filters = [URL.user_id == user.id, URL.deleted_at.is_(None)]
    total_links, total_clicks = (await session.execute(select(func.count(URL.id), func.coalesce(func.sum(URL.click_count), 0)).where(*filters))).one()
    active = await session.scalar(select(func.count()).select_from(URL).where(*filters, URL.is_active.is_(True), or_(URL.expires_at.is_(None), URL.expires_at > now)))
    visible_ids = select(URL.id).where(*filters)
    series = await daily_series(session, [ClickEvent.url_id.in_(visible_ids)], start, days)
    top = (await session.scalars(select(URL).where(*filters).order_by(URL.click_count.desc(), URL.created_at.desc(), URL.id.desc()).limit(5))).all()
    return {"total_links": total_links, "active_links": active, "total_clicks": total_clicks,
            "period_clicks": sum(item["clicks"] for item in series), "clicks_by_day": series,
            "top_links": [link_response(item, request.app.state.settings) for item in top]}


@redirect_router.api_route("/r/{short_code}", methods=["GET", "HEAD"], tags=["Redirects"], response_class=RedirectResponse)
async def redirect(short_code: str, request: Request):
    if not 3 <= len(short_code) <= 32 or any(char not in security.ALPHABET + "_-" for char in short_code):
        raise HTTPException(404, "Link not found")
    cache = request.app.state.cache
    payload, generation = await cache.read(short_code)
    if payload is None:
        async with request.app.state.session_factory() as session:
            link = await session.scalar(select(URL).where(URL.short_code == short_code))
            if link is None:
                raise HTTPException(404, "Link not found")
            payload = {"id": link.id, "original_url": link.original_url, "is_active": link.is_active,
                       "expires_at": link.expires_at.isoformat() if link.expires_at else None,
                       "deleted": link.deleted_at is not None}
        await cache.store(short_code, payload, generation)
    if payload.get("deleted"):
        raise HTTPException(404, "Link not found")
    if not payload["is_active"]:
        raise HTTPException(410, "This link has been paused")
    expiry = datetime.fromisoformat(payload["expires_at"]) if payload["expires_at"] else None
    if expiry is not None and expiry <= utcnow():
        raise HTTPException(410, "This link has expired")
    if request.method == "GET":
        await request.app.state.analytics.record(payload["id"], request.headers.get("referer", ""), request.headers.get("user-agent", ""))
    return RedirectResponse(payload["original_url"], status_code=302,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
