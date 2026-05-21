import importlib


def test_packages_import() -> None:
    for pkg in ("ota_core", "ota_connect", "ota_routines", "ota_dashboard_api"):
        importlib.import_module(pkg)
