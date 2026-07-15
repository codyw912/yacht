import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import (
    Course,
    Regatta,
    RuntimeRecipe,
    SecretReference,
    Vessel,
)
from yacht.runtimes.container import (
    ContainerRuntimeResolutionError,
    resolve_container_runtime,
)


class ContainerRuntimeResolutionTests(unittest.TestCase):
    def test_rejects_vessel_without_runtime(self) -> None:
        regatta = _regatta(vessel_runtime=None)

        with self.assertRaisesRegex(
            ContainerRuntimeResolutionError,
            "vessel baseline does not define a runtime",
        ):
            self._resolve(regatta)

    def test_rejects_non_container_backend(self) -> None:
        regatta = _regatta(backend="host-nix")

        with self.assertRaisesRegex(
            ContainerRuntimeResolutionError,
            "runtime box uses unsupported backend host-nix",
        ):
            self._resolve(regatta)

    def test_rejects_missing_image(self) -> None:
        regatta = _regatta(image=None)

        with self.assertRaisesRegex(
            ContainerRuntimeResolutionError,
            "runtime box is missing image",
        ):
            self._resolve(regatta)

    def test_resolves_docker_command_prefix_with_mounts(self) -> None:
        regatta = _regatta()

        resolution = self._resolve(regatta)

        prefix = resolution.command_prefix
        self.assertEqual(prefix[:4], ("docker", "run", "--rm", "--workdir"))
        self.assertIn("yacht/test-image:1", prefix)
        mounts = [value for flag, value in zip(prefix, prefix[1:]) if flag == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertTrue(any("target=/workspace" in mount for mount in mounts))
        self.assertTrue(any("target=/home/yacht" in mount for mount in mounts))

    def test_secret_refs_label_env_and_file_sources_without_values(self) -> None:
        regatta = _regatta(
            secrets={
                "anthropic": SecretReference(source="env", name="ANTHROPIC_API_KEY"),
                "token": SecretReference(source="file", path="/secrets/token"),
            },
            required_secrets=("anthropic", "token"),
        )

        refs = self._resolve(regatta).secret_refs(regatta)

        self.assertEqual(
            refs,
            (
                {
                    "name": "anthropic",
                    "source": "env",
                    "ref": "ANTHROPIC_API_KEY",
                    "redacted": True,
                },
                {
                    "name": "token",
                    "source": "file",
                    "ref": "/secrets/token",
                    "redacted": True,
                },
            ),
        )

    def test_secret_refs_reject_unresolvable_source(self) -> None:
        regatta = _regatta(
            secrets={"mystery": SecretReference(source="op")},
            required_secrets=("mystery",),
        )

        resolution = self._resolve(regatta)
        with self.assertRaisesRegex(
            ContainerRuntimeResolutionError,
            "secret reference source op is not resolvable",
        ):
            resolution.secret_refs(regatta)

    def test_env_with_secret_values_rejects_file_source(self) -> None:
        regatta = _regatta(
            secrets={"token": SecretReference(source="file", path="/secrets/token")},
            required_secrets=("token",),
        )

        resolution = self._resolve(regatta)
        with self.assertRaisesRegex(
            ContainerRuntimeResolutionError,
            "secret token source file is not supported for runtime env",
        ):
            resolution.env_with_secret_values(regatta, {"token": "value"})

    def test_env_with_secret_values_rejects_missing_value(self) -> None:
        regatta = _regatta(
            secrets={
                "anthropic": SecretReference(source="env", name="ANTHROPIC_API_KEY")
            },
            required_secrets=("anthropic",),
        )

        resolution = self._resolve(regatta)
        with self.assertRaisesRegex(
            ContainerRuntimeResolutionError,
            "missing value for required secret anthropic",
        ):
            resolution.env_with_secret_values(regatta, {})

    def _resolve(self, regatta: Regatta):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            return resolve_container_runtime(
                regatta=regatta,
                vessel=regatta.vessels[0],
                instance_root=root / "instance",
                workspace_path=root / "workspace",
            )


def _regatta(
    *,
    backend: str = "container",
    image: str | None = "yacht/test-image:1",
    vessel_runtime: str | None = "box",
    secrets: dict[str, SecretReference] | None = None,
    required_secrets: tuple[str, ...] = (),
) -> Regatta:
    runtime = RuntimeRecipe(
        name="box",
        backend=backend,
        command=("agent",),
        image=image,
        required_secrets=required_secrets,
    )
    vessel = Vessel(
        name="baseline",
        model="mock",
        rigging=(),
        runtime=vessel_runtime,
    )
    return Regatta(
        name="container-tests",
        course=Course(name="tiny-course", tasks=()),
        vessels=(vessel,),
        secrets=secrets or {},
        runtime_recipes={"box": runtime},
    )


if __name__ == "__main__":
    unittest.main()
