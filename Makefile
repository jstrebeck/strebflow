VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install run resume status test clean

install: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"

run: install
	$(PYTHON) -m attractor run $(ARGS)

resume: install
	$(PYTHON) -m attractor resume $(ARGS)

status: install
	$(PYTHON) -m attractor status $(ARGS)

test: install
	$(PYTHON) -m pytest

clean:
	rm -rf $(VENV)
