from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):

    email: EmailStr

    password: str


class RegisterRequest(BaseModel):

    name: str

    email: EmailStr

    password: str

    role: str


class UserResponse(BaseModel):

    id: int

    name: str

    email: EmailStr

    role: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):

    access_token: str

    token_type: str

    user: UserResponse