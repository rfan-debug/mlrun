import unittest.mock
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Generator

import deepdiff
import pytest
from fastapi.testclient import TestClient

import mlrun.api.utils.singletons.k8s
from mlrun import mlconf
from mlrun.api.db.sqldb.session import _init_engine, create_session
from mlrun.api.initial_data import init_data
from mlrun.api.main import app
from mlrun.api.utils.singletons.db import initialize_db
from mlrun.api.utils.singletons.project_member import initialize_project_member
from mlrun.config import config
from mlrun.utils import logger


@pytest.fixture()
def db() -> Generator:
    """
    This fixture initialize the db singleton (so it will be accessible using mlrun.api.singletons.get_db()
    and generates a db session that can be used by the test
    """
    db_file = NamedTemporaryFile(suffix="-mlrun.db")
    logger.info(f"Created temp db file: {db_file.name}")
    config.httpdb.db_type = "sqldb"
    dsn = f"sqlite:///{db_file.name}?check_same_thread=false"
    config.httpdb.dsn = dsn

    # TODO: make it simpler - doesn't make sense to call 3 different functions to initialize the db
    # we need to force re-init the engine cause otherwise it is cached between tests
    _init_engine(config.httpdb.dsn)

    # forcing from scratch because we created an empty file for the db
    init_data(from_scratch=True)
    initialize_db()
    initialize_project_member()

    # we're also running client code in tests so set dbpath as well
    # note that setting this attribute triggers connection to the run db therefore must happen after the initialization
    config.dbpath = dsn
    yield create_session()
    logger.info(f"Removing temp db file: {db_file.name}")
    db_file.close()


@pytest.fixture()
def client(db) -> Generator:
    with TemporaryDirectory(suffix="mlrun-logs") as log_dir:
        mlconf.httpdb.logs_path = log_dir
        mlconf.runs_monitoring_interval = 0
        mlconf.runtimes_cleanup_interval = 0
        mlconf.httpdb.projects.periodic_sync_interval = "0 seconds"

        with TestClient(app) as c:
            yield c


class K8sSecretsMock:
    def __init__(self):
        # project -> secret_key -> secret_value
        self.project_secrets_map = {}

    def store_project_secrets(self, project, secrets, namespace=""):
        self.project_secrets_map.setdefault(project, {}).update(secrets)

    def delete_project_secrets(self, project, secrets, namespace=""):
        if not secrets:
            self.project_secrets_map.pop(project, None)
        else:
            for key in secrets:
                self.project_secrets_map.get(project, {}).pop(key, None)

    def get_project_secret_keys(self, project, namespace=""):
        return list(self.project_secrets_map.get(project, {}).keys())

    def get_project_secret_data(self, project, secret_keys=None, namespace=""):
        secrets_data = self.project_secrets_map.get(project, {})
        return {
            key: value
            for key, value in secrets_data.items()
            if (secret_keys and key in secret_keys) or not secret_keys
        }

    def assert_project_secrets(self, project: str, secrets: dict):
        assert (
            deepdiff.DeepDiff(
                self.project_secrets_map[project], secrets, ignore_order=True,
            )
            == {}
        )


@pytest.fixture()
def k8s_secrets_mock(client: TestClient) -> K8sSecretsMock:
    logger.info("Creating k8s secrets mock")
    k8s_secrets_mock = K8sSecretsMock()
    config.namespace = "default-tenant"

    mlrun.api.utils.singletons.k8s.get_k8s().is_running_inside_kubernetes_cluster = unittest.mock.Mock(
        return_value=True
    )
    mlrun.api.utils.singletons.k8s.get_k8s().get_project_secret_keys = unittest.mock.Mock(
        side_effect=k8s_secrets_mock.get_project_secret_keys
    )
    mlrun.api.utils.singletons.k8s.get_k8s().get_project_secret_data = unittest.mock.Mock(
        side_effect=k8s_secrets_mock.get_project_secret_data
    )
    mlrun.api.utils.singletons.k8s.get_k8s().store_project_secrets = unittest.mock.Mock(
        side_effect=k8s_secrets_mock.store_project_secrets
    )
    mlrun.api.utils.singletons.k8s.get_k8s().delete_project_secrets = unittest.mock.Mock(
        side_effect=k8s_secrets_mock.delete_project_secrets
    )

    return k8s_secrets_mock
