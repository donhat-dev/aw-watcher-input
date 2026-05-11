.PHONY: build test package clean

PYTHON ?= python
POETRY ?= $(PYTHON) -m poetry
PYINSTALLER ?= $(PYTHON) -m PyInstaller

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
	if [ -f "config.toml.example" ]; then \
		cp config.toml.example dist/aw-watcher-input/config.toml.example; \
	fi
	# if dist/visualization/dist exists, include in package
	if [ -d "visualization/dist" ]; then \
		mkdir -p dist/visualization; \
		cp -r visualization/dist/* dist/visualization; \
	fi

clean:
	rm -rf build dist
	rm -rf aw_watcher_input/__pycache__
