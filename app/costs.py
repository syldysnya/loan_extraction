import hydra
from omegaconf import DictConfig

from app import db
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE

HEADER = ("model", "calls", "failed", "input", "cached", "output", "cost (USD)")
ROW_FORMAT = "{:<24} {:>6} {:>7} {:>10} {:>10} {:>10} {:>12}"


def format_costs(costs: list[db.ModelCost]) -> str:
    lines = [ROW_FORMAT.format(*HEADER)]
    for c in costs:
        lines.append(
            ROW_FORMAT.format(
                c.model_id,
                c.calls,
                c.failed_calls,
                c.input_tokens,
                c.cached_input_tokens,
                c.output_tokens,
                f"{c.cost_usd:.6f}",
            )
        )
    return "\n".join(lines)


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    print(format_costs(db.cost_by_model(db.connect(cfg.db_path), cfg.batch_id)))


if __name__ == "__main__":
    main()
