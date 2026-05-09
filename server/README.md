# Atopsy Backend Server

> Enterprise-grade Node.js + Express + TypeScript backend for the Atopsy AI forensic investigation platform.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Node.js 20+ |
| Framework | Express.js 5 |
| Language | TypeScript 6 (strict) |
| Database | PostgreSQL 16 |
| ORM | Prisma 7 |
| Auth | JWT + Refresh Token Rotation |
| Validation | Zod v4 |
| Logging | Winston + Daily Rotate |
| Security | Helmet, CORS, Rate Limiting, bcrypt |
| DevOps | Docker, PM2 |

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Copy environment variables
cp .env.example .env
# Edit .env with your values

# 3. Generate Prisma client
npm run db:generate

# 4. Run migrations
npm run db:migrate

# 5. Seed the database
npm run db:seed

# 6. Start development server
npm run dev
```

## Docker

```bash
# Start PostgreSQL + Server
docker-compose up -d

# Run migrations inside container
docker exec atopsy-server npx prisma migrate deploy
```

## API Endpoints

### Auth (`/api/v1/auth`)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/signup` | ❌ | Register new user |
| POST | `/login` | ❌ | Login + get tokens |
| POST | `/refresh-token` | ❌ | Rotate tokens |
| POST | `/logout` | ✅ | Invalidate session |
| GET | `/me` | ✅ | Current user profile |
| POST | `/change-password` | ✅ | Change password |

### Users (`/api/v1/users`) — Admin Only
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List users (paginated) |
| GET | `/:id` | Get user details |
| PATCH | `/:id/role` | Update user role |
| PATCH | `/:id/deactivate` | Deactivate user |
| PATCH | `/:id/reactivate` | Reactivate user |

### Investigations (`/api/v1/investigations`)
| Method | Endpoint | Roles | Description |
|--------|----------|-------|-------------|
| POST | `/` | ADMIN, INVESTIGATOR | Create investigation |
| GET | `/` | All authed | List (paginated, searchable) |
| GET | `/:id` | All authed | Get with evidence + reports |
| PATCH | `/:id` | ADMIN, INVESTIGATOR | Update investigation |
| DELETE | `/:id` | ADMIN | Delete investigation |

### Evidence (`/api/v1/evidence`)
| Method | Endpoint | Roles | Description |
|--------|----------|-------|-------------|
| POST | `/` | All authed | Add evidence |
| GET | `/investigation/:id` | All authed | List by investigation |
| GET | `/:id` | All authed | Get evidence details |
| DELETE | `/:id` | ADMIN | Delete evidence |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check + uptime |

## Security Features

- ✅ Helmet security headers
- ✅ Strict CORS with origin whitelist
- ✅ Global + endpoint-specific rate limiting
- ✅ JWT access tokens (15min expiry)
- ✅ HTTP-only refresh token cookies (7d, SameSite=Strict)
- ✅ Refresh token rotation with family-based reuse detection
- ✅ Account lockout after 5 failed login attempts
- ✅ bcrypt password hashing (12 rounds)
- ✅ Strong password policy enforcement
- ✅ Zod input validation on all endpoints
- ✅ Prisma parameterized queries (SQL injection proof)
- ✅ No stack traces in production responses
- ✅ Structured audit logging for security events
- ✅ Request ID tracking
- ✅ Body size limits (10MB)

## Default Seed Users

| Email | Password | Role |
|-------|----------|------|
| admin@atopsy.io | Admin@123456 | ADMIN |
| investigator@atopsy.io | Invest@123456 | INVESTIGATOR |
| expert@atopsy.io | Expert@123456 | FORENSIC_EXPERT |
