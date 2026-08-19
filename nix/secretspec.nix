# Project-local SecretSpec build.
#
# Why this file exists: nixpkgs trails upstream SecretSpec (nixpkgs ships
# 0.18.0 while upstream released 0.19.1), and Yacht's contributor
# environment pins the release it documents. The derivation follows the
# standard nixpkgs `buildRustPackage` + `fetchCrate` pattern so it can be
# dropped in favour of `pkgs.secretspec` once nixpkgs catches up.
#
# Updating: see docs/reference/secrets.md ("Updating the pinned SecretSpec
# release"). `nix run .#update-secretspec` is not wired up; use the
# passthru update hook:
#
#   nix-shell -p nix-update --run \
#     'nix-update --file nix/secretspec.nix --version <new> secretspec'
#
# or bump `version`, set both hashes to `lib.fakeHash`, and let two failed
# builds report the real values.
{
  lib,
  rustPlatform,
  fetchCrate,
  fetchurl,
  cacert,
  jq,
  sops,
  nix-update-script,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "secretspec";
  version = "0.19.1";

  src = fetchCrate {
    inherit (finalAttrs) pname version;
    hash = "sha256-hntOPTOrCfVWE4MaNmXfPQ4WAlOG1CFG5/ykSyviJ3A=";
  };

  cargoHash = "sha256-KRC3b6AqSYxjSInULchYNQGm9hw97lDws0+stFZasmc=";

  # The published crate omits the test fixture its suite shells out to.
  postPatch = ''
    mkdir -p ../tests/fixtures
    cp ${
      fetchurl {
        url = "https://raw.githubusercontent.com/cachix/secretspec/v${finalAttrs.version}/tests/fixtures/bw-shim.sh";
        hash = "sha256-Xg1d8h2DOA6p0Hn9xP9TYzFN1863Wyk3QuQlFk+Y0ME=";
      }
    } ../tests/fixtures/bw-shim.sh
    chmod +x ../tests/fixtures/bw-shim.sh
    patchShebangs ../tests/fixtures/bw-shim.sh
  '';

  nativeCheckInputs = [
    jq
    sops
  ];

  preCheck = ''
    export HOME="$TMPDIR"
    export SSL_CERT_FILE="${cacert}/etc/ssl/certs/ca-bundle.crt"
  '';

  # A test binds to localhost, which requires an explicit Darwin sandbox exception.
  __darwinAllowLocalNetworking = true;

  passthru.updateScript = nix-update-script { };

  meta = {
    description = "Declarative secrets, every environment, any provider";
    homepage = "https://secretspec.dev";
    changelog = "https://github.com/cachix/secretspec/blob/v${finalAttrs.version}/CHANGELOG.md";
    license = lib.licenses.asl20;
    mainProgram = "secretspec";
  };
})
