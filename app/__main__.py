import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:get_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
