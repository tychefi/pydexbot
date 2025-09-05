# Poetry Initialization Guide

## 1. Install Poetry

It is recommended to use the official installation script:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

## 2. Initialize the Project

Run the following command in the project root directory:

```bash
poetry init --no-interaction --name pydexbot --description "A Python bot project managed by Poetry" --author "tychefi" --python "^3.9.1"
```

This command will automatically generate the `pyproject.toml` file, including project name, description, author, and Python version requirement.

## 3. Add Dependencies

To add a dependency, for example requests:

```bash
poetry add requests
```

## 4. Common Commands

- Install all dependencies:
  ```bash
  poetry install
  ```
- Run the main program:
  ```bash
  poetry run python swap_bot_py/main.py
  ```
- Add development dependencies (e.g. pytest):
  ```bash
  poetry add --dev pytest
  ```

## 5. Recommended Directory Structure

- Source code in `swap_bot_py/` directory
- Test code in `tests/` directory
- Documentation in `docs/` directory
- Ignore files in `.gitignore`
- Project description in `README.md`
- Project configuration in `pyproject.toml`
