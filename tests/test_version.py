"""One version, from the package metadata (pyproject.toml)."""

from importlib.metadata import version


def test_package_version_comes_from_the_metadata():
    import ifdd.be.core

    assert ifdd.be.core.__version__ == version("ifdd-be-core")


def test_instance_version_defaults_to_the_package_version():
    from ifdd.be.core.config import CoreSettings

    assert CoreSettings(_env_file=None).IFDD_BE_VERSION == version("ifdd-be-core")


def test_api_version_setting_is_gone():
    # Spec, log and /version all use IFDD_BE_VERSION; a leftover API_VERSION
    # in an old .env is ignored.
    from ifdd.be.core.config import CoreSettings

    settings = CoreSettings(_env_file=None, API_VERSION="2025.5.1")
    assert not hasattr(settings, "API_VERSION")
