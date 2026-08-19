from dataclasses import dataclass

from fastapi.templating import Jinja2Templates

from app.api.service_token import ServiceTokenVerifier
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
    # 새록이 보내는 dou-connect 서비스 토큰 검증 (직원 조회·service 모드 환자 목록)
    service_verifier: ServiceTokenVerifier


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

    service_verifier = ServiceTokenVerifier.from_jwks_url(
        jwks_url=settings.dou_connect_jwks_url,
        issuer=settings.dou_connect_issuer,
        audience=settings.service_token_audience,
    )

    return AppState(
        settings=settings,
        store=store,
        signer=signer,
        oauth_service=oauth_service,
        templates=templates,
        service_verifier=service_verifier,
    )
