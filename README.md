
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
