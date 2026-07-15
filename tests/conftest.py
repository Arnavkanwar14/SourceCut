from __future__ import annotations

from pathlib import Path

import pytest

from app import main, production


@pytest.fixture(scope="session", autouse=True)
def isolate_test_runtime(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Keep test projects, uploads, and renders out of the user's local library."""
    runtime = tmp_path_factory.mktemp("sourcecut-runtime")
    previous_main_root = main.ROOT
    previous_main_db = main.DB_PATH
    previous_production_db = production.DB_PATH
    previous_output_dir = production.OUTPUT_DIR
    main.ROOT = runtime
    main.DB_PATH = runtime / "sourcecut.db"
    production.DB_PATH = main.DB_PATH
    production.OUTPUT_DIR = runtime / "outputs"
    try:
        main.init_db()
        yield
    finally:
        main.ROOT = previous_main_root
        main.DB_PATH = previous_main_db
        production.DB_PATH = previous_production_db
        production.OUTPUT_DIR = previous_output_dir
