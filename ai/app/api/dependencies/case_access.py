import uuid
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy import text, or_
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.case import Case

bearer = HTTPBearer()


def current_investigator(credentials: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    try:
        if not settings.JWT_ACCESS_SECRET:
            raise ValueError('Node access-token secret is not configured')
        payload = jwt.decode(credentials.credentials, settings.JWT_ACCESS_SECRET, algorithms=['HS256'],
            options={'require_exp': True})
        user_id, session_id = uuid.UUID(payload['userId']), uuid.UUID(payload['sessionId'])
        user = db.query(User).filter_by(id=user_id, is_active=True).first()
        session = db.execute(text('SELECT "userId", "isValid", "expiresAt" FROM sessions WHERE id = :id'), {'id': session_id}).mappings().first()
        if not user or not session or session['userId'] != user_id or not session['isValid']:
            raise ValueError('Session is invalid')
        expiry = session['expiresAt'].replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise ValueError('Session expired')
        return user
    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Invalid or expired application session')


def allowed_cases(db, user):
    query = db.query(Case)
    if user.role != 'ADMIN':
        query = query.filter(or_(Case.created_by == user.id, Case.assigned_to == user.id))
    return query


def require_case(db, user, case_id):
    case = allowed_cases(db, user).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(404, 'Investigation not found')
    return case
