
# pydexbot

Quant Swap Bot project, managed with Poetry for dependency and build management.

## Directory Structure

```
pydexbot/    # Main source code directory
	 config.py
	 main.py
	 swap.py
	 utils.py

README.md       # Project documentation
pyproject.toml  # Poetry project configuration
.gitignore      # Ignore file

Place your test code in the `tests/` directory. It is recommended to use pytest.
```

## Quick Start

1. Install Poetry (already done)
2. Install dependencies:
	```bash
	poetry install
	```
3. Run the main program:
	```bash
	poetry run python pydexbot/main.py
	```

## Dependency Management

All dependencies are declared in `pyproject.toml`. It is recommended to use Poetry for installation and management.

## Testing

Place your test code in the `tests/` directory. It is recommended to use pytest.

## Configuration

The bot loads runtime settings from `./config/.config.yaml` if it exists. This file should contain deployment-specific values and secrets, and it should not be committed to Git.

Use `./config/config.example.yaml` as the template for your configuration. Copy it to `.config.yaml` and update values for the target environment.

Example:

```bash
cp config/config.example.yaml config/.config.yaml
vim config/.config.yaml
```

Notes:

- `https://t.flonscan.io` is the testnet endpoint.
- `https://m.flonscan.io` is the mainnet endpoint.
- `config/config.example.yaml` is a template, not the active runtime config.
- `config/.config.yaml` is ignored by `.gitignore` to keep secrets safe.
- `min_interval_seconds` and `max_interval_seconds` are local polling intervals after a successful push. Keep them below the smallest on-chain `min_trade_seconds`; `tokenx.mm::schedules` controls the actual next trade readiness.
- `ready_jitter_seconds` adds a final delay after the contract schedule is ready, so multiple pairs do not submit at an exact fixed second.

## Adding a new trading pair

To add a new market for automatic market making trading:

1. Open your active runtime config file:
   ```bash
   vim config/.config.yaml
   ```
2. Add the new trading pair string to the `trade_pairs` list.
   ```yaml
   trade_pairs:
     - "flon.usdt"
     - "sing.usdt"
     - "newtoken.usdt"
   ```
3. Make sure the new pair is configured on-chain:
   - `bot.mm::botgroups` must contain a bot group named exactly the pair string.
   - `buylowsellhi::trademarkets` must contain a market row named exactly the pair string.
4. Ensure the new bot group has at least one bot account with sufficient balance, and that the market liquidity is funded.
5. Restart the bot service or container so it reloads the updated config.

Notes:
- The pair name in `trade_pairs` must match the on-chain market and bot group exactly.
- If you make this change in `config/config.example.yaml`, copy it to `config/.config.yaml` or repeat it there for the active runtime.
- The service uses `config/.config.yaml` when present, so the example file is only a template.
