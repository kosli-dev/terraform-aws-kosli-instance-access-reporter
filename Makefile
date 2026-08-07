# Test runner for the lambda source under deployment/.
#
# uv builds a throwaway environment from deployment/requirements-test.txt on
# each run, so there is nothing to create or activate first, and nothing to
# keep in step when the pins change. It downloads the interpreter too, so the
# Python on your PATH does not matter.
#
# The version and the requirements file are the ones CI uses - see
# .github/workflows/. Keep the three in step.

PYTHON_VERSION ?= 3.14
UV ?= uv

# --no-project: there is no pyproject.toml here, and without this uv searches
# upwards and adopts whichever one it finds in a parent directory.
UV_RUN = $(UV) run --no-project --python $(PYTHON_VERSION) \
	--with-requirements deployment/requirements-test.txt

# Passed through to pytest: make test ARGS="-k elevation -x"
ARGS ?=

.DEFAULT_GOAL := test

.PHONY: test
test:
	$(UV_RUN) python -m pytest -q $(ARGS)

.PHONY: fmt
fmt:
	terraform fmt --recursive
