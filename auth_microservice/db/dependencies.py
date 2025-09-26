from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from taskiq import TaskiqDepends


async def get_db_session(
    request: Request = TaskiqDepends(),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Create and get database session.

    :param request: current request.
    :yield: database session.
    """
    session: AsyncSession = request.app.state.db_session_factory()

    try:
        yield session
    except Exception:  # pragma: no cover - defensive, exercised via integration tests
        await session.rollback()
        raise
    else:
        await session.commit()
    finally:
        await session.close()
