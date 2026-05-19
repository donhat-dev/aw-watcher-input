.PHONY: build test package clean

PYTHON ?= python
POETRY ?= poetry
PYINSTALLER ?= $(POETRY) run python -m PyInstaller

build:
	$(POETRY) install

test:
	$(POETRY) run aw-watcher-input --help  # Ensures that it at least starts
	make typecheck

typecheck:
	$(POETRY) run mypy src/aw_watcher_input --ignore-missing-imports

build-vis:
	#npm install -g pug-cli browserify
	cd visualization && make build

package:
	$(PYINSTALLER) aw-watcher-input.spec --clean --noconfirm
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "$$target = 'dist/aw-watcher-input'; if ((Test-Path $$target) -and -not (Test-Path $$target -PathType Container)) { Move-Item $$target ($$target + '.bin') -Force; New-Item -ItemType Directory -Force $$target | Out-Null; Move-Item ($$target + '.bin') (Join-Path $$target 'aw-watcher-input') -Force } else { New-Item -ItemType Directory -Force $$target | Out-Null }; if (Test-Path 'config.toml.example') { Copy-Item 'config.toml.example' 'dist/aw-watcher-input/config.toml.example' -Force }; if (Test-Path 'visualization/dist') { New-Item -ItemType Directory -Force 'dist/visualization' | Out-Null; Copy-Item 'visualization/dist/*' 'dist/visualization' -Recurse -Force }"
else
	if [ -f "dist/aw-watcher-input" ]; then \
		mv dist/aw-watcher-input dist/aw-watcher-input.bin; \
		mkdir -p dist/aw-watcher-input; \
		mv dist/aw-watcher-input.bin dist/aw-watcher-input/aw-watcher-input; \
	else \
		mkdir -p dist/aw-watcher-input; \
	fi
	if [ -f "config.toml.example" ]; then \
		cp config.toml.example dist/aw-watcher-input/config.toml.example; \
	fi
	# if dist/visualization/dist exists, include in package
	if [ -d "visualization/dist" ]; then \
		mkdir -p dist/visualization; \
		cp -r visualization/dist/* dist/visualization; \
	fi
endif

clean:
	rm -rf build dist
	rm -rf aw_watcher_input/__pycache__
