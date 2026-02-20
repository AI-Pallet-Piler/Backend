from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.inventory import router as inventory_router
from app.api.v1.endpoints.orders import router as orders_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.user_service_users import router as user_service_users_router
from app.db import create_tables, get_db, engine
from app.models import User, UserRole
from app.core.security import hash_password
from app.services.packing_service import start_packing_service
from app.add_initial_users import add_initial_users
from app.add_initial_orders import create_test_data


async def seed_initial_users():
    """Create initial users if they don't exist."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(engine, class_=AS, expire_on_commit=False)
    
    initial_users = [
        {"name": "Admin User", "email": "admin@example.com", "badge_number": "ADMIN001", "password": "admin123", "role": UserRole.ADMIN},
        {"name": "Manager User", "email": "manager@example.com", "badge_number": "MGR001", "password": "manager123", "role": UserRole.MANAGER},
        {"name": "Picker User", "email": "picker@example.com", "badge_number": "PICK001", "password": "picker123", "role": UserRole.PICKER},
    ]
    
    async with async_session() as session:
        for user_data in initial_users:
            result = await session.execute(select(User).where(User.email == user_data["email"]))
            if result.scalar_one_or_none() is None:
                user = User(
                    name=user_data["name"],
                    email=user_data["email"],
                    badge_number=user_data["badge_number"],
                    hashed_password=hash_password(user_data["password"]),
                    role=user_data["role"],
                )
                session.add(user)
                print(f"Created user: {user_data['email']}")
        await session.commit()



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await create_tables()
    print("Database tables created successfully!")
    
    # Start packing service for automatic order processing
    await start_packing_service()
    print("Packing service started!")
    await add_initial_users()
    await create_test_data()

    yield  # Application runs while inside this block

    print("Application is shutting down...")


app = FastAPI(lifespan=lifespan, redirect_slashes=False)

# CORS configuration for development: allow the local Vite dev server and the LAN IP address used.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.0.204:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",        
    "http://127.0.0.1:3000",       
    "http://192.168.0.204:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_service_users_router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "hello world"}

# Simple db connection test endpoint
@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "connected"}