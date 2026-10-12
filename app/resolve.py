import hydra
from omegaconf import DictConfig

from app import db
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE
from app.resolution.resolve import resolve_all


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    resolve_all(db.connect(cfg.db_path))


if __name__ == "__main__":
    main()
