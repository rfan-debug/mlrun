# Copyright 2018 Iguazio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from contextlib import contextmanager
from os import environ
from tempfile import NamedTemporaryFile

import pytest
import requests_mock as requests_mock_package
import yaml

from mlrun import config as mlconf

ns_env_key = f"{mlconf.env_prefix}NAMESPACE"


@pytest.fixture
def config():
    old = mlconf.config
    mlconf.config = mlconf.dynamic.Config.from_dict(mlconf.default_config)
    mlconf.loader.ConfigLoader.loaded = False

    yield mlconf.config

    mlconf.config = old
    mlconf.loader.ConfigLoader.loaded = False


@contextmanager
def patch_env(kw):
    old, new = [], []
    for key, value in kw.items():
        old_val = environ.get(key)
        if old_val:
            old.append((key, old_val))
        else:
            new.append(key)
        environ[key] = value

    yield

    for key, value in old:
        environ[key] = value
    for key in new:
        del environ[key]


def test_nothing(config):
    expected = mlconf.default_config["namespace"]
    assert config.namespace == expected, "namespace changed"


def create_yaml_config(**kw):
    tmp = NamedTemporaryFile(mode="wt", suffix=".yml", delete=False)
    yaml.dump(kw, tmp, default_flow_style=False)
    tmp.flush()
    return tmp.name


def test_file(config):
    ns = "banana"
    config_path = create_yaml_config(namespace=ns)

    with patch_env({mlconf.env_file_key: config_path}):
        mlconf.config.reload()

    assert config.namespace == ns, "not populated from file"


def test_env(config):
    ns = "orange"
    with patch_env({ns_env_key: ns}):
        mlconf.config.reload()

    assert config.namespace == ns, "not populated from env"


def test_env_override(config):
    env_ns = "daffy"
    config_ns = "bugs"

    config_path = create_yaml_config(namespace=config_ns)
    env = {
        mlconf.env_file_key: config_path,
        ns_env_key: env_ns,
    }

    with patch_env(env):
        mlconf.config.reload()

    assert config.namespace == env_ns, "env did not override"


old_config_value = None
new_config_value = "blabla"


def test_overriding_config_not_remain_for_next_tests_setter():
    global old_config_value, new_config_value
    old_config_value = mlconf.config.igz_version
    mlconf.config.igz_version = new_config_value
    mlconf.config.httpdb.data_volume = new_config_value


def test_overriding_config_not_remain_for_next_tests_tester():
    global old_config_value
    assert old_config_value == mlconf.config.igz_version
    assert old_config_value == mlconf.config.httpdb.data_volume


def test_iguazio_api_url_resolution():
    # nothing configured should return nothing
    assert mlconf.config.iguazio_api_url == ""
    # only docker registry configured (as in open source) - can't resolve
    mlconf.config.httpdb.builder.docker_registry = "index.docker.io/some-user"
    assert mlconf.config.iguazio_api_url == ""
    # unknown format for docker registry configured - can't resolve
    mlconf.config.httpdb.builder.docker_registry = "io/some-user"
    mlconf.config.igz_version = "1.2.3"
    assert mlconf.config.iguazio_api_url == ""
    # known format docker registry configured - can resolve
    mlconf.config.httpdb.builder.docker_registry = (
        "docker-registry.default-tenant.app.hedingber-301-1.iguazio-cd2.com:80"
    )
    mlconf.config.igz_version = "1.2.3"
    assert (
        mlconf.config.iguazio_api_url
        == "https://dashboard.default-tenant.app.hedingber-301-1.iguazio-cd2.com"
    )
    # value configured - no resolution needed
    url = "some-url"
    mlconf.config._iguazio_api_url = url
    assert mlconf.config.iguazio_api_url == url


def test_setting_dbpath_trigger_connect(requests_mock: requests_mock_package.Mocker):
    api_url = "http://mlrun-api-url:8080"
    remote_host = "some-namespace"
    response_body = {
        "version": "some-version",
        "remote_host": remote_host,
    }
    requests_mock.get(f"{api_url}/api/client-spec", json=response_body)
    assert "" == mlconf.config.remote_host
    mlconf.config.dbpath = api_url
    assert remote_host == mlconf.config.remote_host
