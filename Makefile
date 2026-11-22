.PHONY: build validate smoke report sync-palette

PYTHON ?= python3
VIM ?= vim

build:
	$(PYTHON) build.py

validate:
	$(PYTHON) build.py --check
	$(PYTHON) validate.py
	$(VIM) -Nu NONE -es -S test/smoke.vim

smoke:
	$(VIM) -Nu NONE -es -S test/smoke.vim

report:
	$(PYTHON) build.py --report

sync-palette:
	cp ../42vibes-palette/palette.json vendor/palette.json
	@echo "vendor/palette.json aktualisiert -- danach 'make build validate'"
