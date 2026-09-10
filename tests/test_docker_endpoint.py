import re
import unittest

from tests.fixtures import docker_endpoint_selection
from yacht.domain.model import ConfigError
from yacht.runtimes.docker_endpoint import docker_socket_bind_spec


class DockerEndpointTests(unittest.TestCase):
    def test_rejects_malformed_unix_endpoints(self) -> None:
        endpoints = (
            "unix://other/tmp/docker.sock",
            "unix:///tmp/docker.sock#rootless",
            "unix:///tmp/docker.sock?x",
            "unix:///tmp/a:b.sock",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                with docker_endpoint_selection(host=endpoint, context=None):
                    with self.assertRaisesRegex(ConfigError, re.escape(endpoint)):
                        docker_socket_bind_spec()
