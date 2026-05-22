from dataclasses import dataclass

from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.oauth.jwt_signer import JwtSigner
from app.oauth.service import OAuthService
from app.storage.memory import InMemoryStore
from app.storage.seed import seed_store


@dataclass
class AppState:
    settings: Settings
    store: InMemoryStore
    signer: JwtSigner
    oauth_service: OAuthService
    templates: Jinja2Templates


def build_app_state(settings: Settings) -> AppState:
    store = InMemoryStore()
    seed_store(store)

    signer = JwtSigner.from_paths(
        issuer=settings.jwt_issuer,
        private_key_path=settings.jwt_private_key_path,
        public_key_path=settings.jwt_public_key_path,
    )

    oauth_service = OAuthService(
        store=store,
        signer=signer,
        client_id=settings.saylog_client_id,
        client_secret=settings.saylog_client_secret.get_secret_value(),
        redirect_uri=settings.saylog_redirect_uri,
        audience="saylog",
        access_ttl=settings.jwt_access_token_ttl,
        refresh_ttl=settings.jwt_refresh_token_ttl,
    )

    templates = Jinja2Templates(directory="app/oauth/templates")

    return AppState(
        settings=settings,
        store=store,
        signer=signer,
        oauth_service=oauth_service,
        templates=templates,
    )
