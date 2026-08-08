# Canonical developer and CI entry points.
#
# CI runs exactly these targets, so `make lint` and `make test` on a laptop
# check the same things a pull request will.

SHELL := /bin/bash
PYTHON ?= python3
RUFF := $(PYTHON) -m ruff

# Django test labels. Override to run a subset, e.g.
#   make test TEST_LABELS=species.tests.test_models
TEST_LABELS ?= species.tests pending_actions.tests
TEST_VERBOSITY ?= 2

COMPOSE_TEST := docker compose -f docker-compose.test.yml

.DEFAULT_GOAL := help
.PHONY: help dev-install lint lint-fix test test-db-up test-db-down

help:
	@echo 'make dev-install   install runtime + tooling dependencies'
	@echo 'make lint          run ruff check and the formatter in check mode (CI runs this)'
	@echo 'make lint-fix      apply ruff autofixes and reformat'
	@echo 'make test          run the Django test suite (CI runs this)'
	@echo 'make test-db-up    start a local MariaDB matching the CI service'
	@echo 'make test-db-down  stop it'

dev-install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(RUFF) check .
	$(RUFF) format --check .

lint-fix:
	$(RUFF) check --fix .
	$(RUFF) format .

test:
	source ./test.env && \
	mkdir -p "$$MEDIA_ROOT" "$$STATIC_ROOT" && \
	cd speciesnet && $(PYTHON) manage.py test --noinput $(TEST_LABELS) -v $(TEST_VERBOSITY)

test-db-up:
	$(COMPOSE_TEST) up -d test_db

test-db-down:
	$(COMPOSE_TEST) down -v
