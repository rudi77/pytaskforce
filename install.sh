#!/usr/bin/env sh
# Taskforce Community — native installer for Linux and macOS.
#
# Quick start:
#   curl -LsSf https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.sh | sh
#
# Install from source instead of a prebuilt bundle:
#   curl -LsSf https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.sh | sh -s -- --from-source
#
# This installs the Community edition only. For Enterprise use the
# installer in the taskforce-enterprise repository.
set -eu

REPO="rudi77/pytaskforce"
APP_NAME="taskforce"
INSTALL_HOME="${TASKFORCE_HOME:-$HOME/.taskforce}"
BIN_DIR="${TASKFORCE_BIN_DIR:-$HOME/.local/bin}"
MODE="binary"
VERSION="${TASKFORCE_VERSION:-latest}"

for arg in "$@"; do
  case "$arg" in
    --from-source) MODE="source" ;;
    --binary)      MODE="binary" ;;
    --version=*)   VERSION="${arg#*=}" ;;
    -h|--help)
      cat <<'EOF'
Taskforce Community installer

  --from-source     Clone the repository and install via uv (needs git).
  --binary          Download a prebuilt bundle from GitHub Releases (default).
  --version=X.Y.Z   Install a specific release/branch (default: latest).

Environment overrides:
  TASKFORCE_HOME      Install directory      (default: ~/.taskforce)
  TASKFORCE_BIN_DIR   Launcher location      (default: ~/.local/bin)
  TASKFORCE_VERSION   Release/branch to use  (default: latest)
EOF
      exit 0 ;;
    *) printf 'error: unknown option: %s\n' "$arg" >&2; exit 1 ;;
  esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$1" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

detect_platform() {
  os="$(uname -s)"; arch="$(uname -m)"
  case "$os" in
    Linux)  OS="linux" ;;
    Darwin) OS="macos" ;;
    *) die "unsupported OS: $os — retry with --from-source" ;;
  esac
  case "$arch" in
    x86_64|amd64)  ARCH="x64" ;;
    arm64|aarch64) ARCH="arm64" ;;
    *) die "unsupported architecture: $arch" ;;
  esac
}

install_binary() {
  detect_platform
  need curl; need tar
  asset="taskforce-community-${OS}-${ARCH}.tar.gz"
  if [ "$VERSION" = "latest" ]; then
    url="https://github.com/$REPO/releases/latest/download/$asset"
  else
    url="https://github.com/$REPO/releases/download/v${VERSION#v}/$asset"
  fi
  say "Downloading $asset ..."
  tmp="$(mktemp -d)"
  if ! curl -fLsS "$url" -o "$tmp/$asset"; then
    rm -rf "$tmp"
    die "no prebuilt bundle for ${OS}-${ARCH} ($VERSION).
Retry installing from source:
  curl -LsSf https://raw.githubusercontent.com/$REPO/main/install.sh | sh -s -- --from-source"
  fi
  say "Extracting to $INSTALL_HOME/bundle ..."
  rm -rf "$INSTALL_HOME/bundle"
  mkdir -p "$INSTALL_HOME/bundle"
  tar -xzf "$tmp/$asset" -C "$INSTALL_HOME/bundle" --strip-components=1
  rm -rf "$tmp"
  [ -x "$INSTALL_HOME/bundle/$APP_NAME" ] || die "bundle did not contain a '$APP_NAME' executable"
  RUN_LINE="exec \"$INSTALL_HOME/bundle/$APP_NAME\" \"\$@\""
}

install_source() {
  need git
  if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv (Python package manager) ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi
  need uv
  src="$INSTALL_HOME/src"
  if [ "$VERSION" = "latest" ]; then ref=""; else ref="$VERSION"; fi
  if [ -d "$src/.git" ]; then
    say "Updating existing checkout ..."
    git -C "$src" fetch --depth 1 origin "${ref:-HEAD}"
    git -C "$src" checkout -f FETCH_HEAD
  else
    say "Cloning $REPO ..."
    rm -rf "$src"
    if [ -n "$ref" ]; then
      git clone --depth 1 --branch "$ref" "https://github.com/$REPO.git" "$src"
    else
      git clone --depth 1 "https://github.com/$REPO.git" "$src"
    fi
  fi
  say "Installing dependencies with uv (downloads Python + packages) ..."
  ( cd "$src" && uv sync --frozen )
  say "Installing the Chromium browser for the browser tool ..."
  ( cd "$src" && uv run playwright install chromium ) \
    || warn "playwright install failed — the browser tool will be unavailable"
  if command -v corepack >/dev/null 2>&1 || command -v pnpm >/dev/null 2>&1; then
    say "Building the web UI ..."
    if ( cd "$src/ui" \
         && (corepack enable >/dev/null 2>&1 || true) \
         && pnpm install --frozen-lockfile \
         && pnpm run build ); then
      rm -rf "$src/src/taskforce/api/_ui"
      cp -r "$src/ui/dist" "$src/src/taskforce/api/_ui"
    else
      warn "UI build failed — the web UI will be unavailable (REST API still works)"
    fi
  else
    warn "pnpm/corepack not found — skipping web UI build (REST API still works)"
  fi
  RUN_LINE="exec uv run --project \"$src\" taskforce \"\$@\""
}

setup_env() {
  mkdir -p "$INSTALL_HOME"
  env_file="$INSTALL_HOME/.env"
  if [ -f "$env_file" ]; then
    say "Keeping existing configuration at $env_file"
    return
  fi
  key=""
  if [ -t 0 ]; then
    printf 'Enter your OpenAI API key (leave blank to configure later): '
    read -r key || key=""
  fi
  {
    echo "# Taskforce configuration — edit any time, then restart 'taskforce up'."
    if [ -n "$key" ]; then
      echo "OPENAI_API_KEY=$key"
    else
      echo "# OPENAI_API_KEY=sk-..."
    fi
    echo "# Other providers / tools — see .env.example in the repository."
  } > "$env_file"
  chmod 600 "$env_file"
  say "Wrote configuration to $env_file"
}

write_launcher() {
  mkdir -p "$INSTALL_HOME/app" "$BIN_DIR"
  launcher="$INSTALL_HOME/app/$APP_NAME"
  {
    echo '#!/usr/bin/env sh'
    echo '# Generated by the Taskforce installer — do not edit.'
    echo 'set -a'
    echo "[ -f \"$INSTALL_HOME/.env\" ] && . \"$INSTALL_HOME/.env\""
    echo 'set +a'
    echo "$RUN_LINE"
  } > "$launcher"
  chmod +x "$launcher"
  ln -sf "$launcher" "$BIN_DIR/$APP_NAME"
  say "Linked $BIN_DIR/$APP_NAME"
}

main() {
  say "Installing Taskforce Community ($MODE mode) ..."
  case "$MODE" in
    binary) install_binary ;;
    source) install_source ;;
  esac
  setup_env
  write_launcher
  echo
  say "Taskforce Community installed."
  case ":$PATH:" in
    *":$BIN_DIR:"*) : ;;
    *) warn "$BIN_DIR is not on your PATH — add this to your shell profile:"
       printf '       export PATH="%s:$PATH"\n' "$BIN_DIR" ;;
  esac
  echo
  echo "  Next steps:"
  echo "    taskforce up        # start Taskforce and open the web UI"
  echo
}

main
