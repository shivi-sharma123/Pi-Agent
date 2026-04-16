import asyncio
from shared.db.models import Base
from shared.db.session import _engine

async def main():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(main())
