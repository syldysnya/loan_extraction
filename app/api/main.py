import hydra
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from omegaconf import DictConfig

from app.api import borrowers_api, health_api
from app.api.request_id import RequestIDMiddleware
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE

TITLE = "Loan Extraction API"
DESCRIPTION = "Read-only access to borrower records extracted from loan documents, with every value's sources."
VERSION = "1.0.0"
GZIP_MIN_BYTES = 1000  # records with all their sources can be large


def create_app(db_path: str) -> FastAPI:
    app = FastAPI(title=TITLE, description=DESCRIPTION, version=VERSION)
    app.state.db_path = db_path

    app.include_router(borrowers_api.router)
    app.include_router(health_api.router)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    # Production: a frontend on another origin would need CORS, limited to that origin:
    #     app.add_middleware(CORSMiddleware, allow_origins=[frontend_url], allow_methods=["GET"])
    # Here the API is bound to localhost and has no browser client.
    return app


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    # log_config=None keeps Hydra's logging (plain stdout + JSON file) instead of Uvicorn's own.
    # access_log=False: RequestIDMiddleware already logs each request, with its request ID.
    uvicorn.run(create_app(cfg.db_path), host=cfg.api.host, port=cfg.api.port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
