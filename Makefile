# Makefile - PiWatcher development and deployment
.PHONY: lint typecheck test test-cov base-db-up base-migrate base-llama-up base-inference-up base-up deploy-base deploy-camera deploy-inference update-cameras setup-camera

# Configuration
CAMERAS ?= feeder-cam.local pond-cam.local
CAMERA_SRC := packages/camera/src/piwatcher_camera/
CAMERA_DEST := ~/piwatcher/
CAMERA_USER ?= pi
CAMERA_SERVICE := piwatcher-camera
ENABLE_INFERENCE ?= false
BASE_UP_DEPS := base-db-up base-migrate

ifeq ($(ENABLE_INFERENCE),true)
BASE_UP_DEPS += base-inference-up
endif

# Development
lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run ty check

test:
	uv run pytest

test-cov:
	uv run pytest --cov=packages/camera/src --cov=packages/base/src --cov-report=term-missing

# Base station
base-db-up:
	docker compose up -d postgres

base-llama-up:
	LLAMA_SWAP_RUNTIME=docker bash deploy/setup-llama-swap.sh
	docker compose up -d llama-swap

base-inference-up: base-llama-up

base-migrate:
	cd packages/base && uv run alembic upgrade head

base-up: $(BASE_UP_DEPS)
	uv run --package piwatcher-base piwatcher-server

# Deployment
deploy-camera:
	@if [ -z "$(CAM)" ] && [ -z "$(CAMERA_ENV_FILE)" ]; then \
		echo "Usage: make deploy-camera CAM=pizero.local CAMERA_USER=pizero"; \
		echo "   or: make deploy-camera CAMERA_ENV_FILE=deploy/cameras/roomtest.env"; \
		exit 1; \
	fi
	@if [ -n "$(CAMERA_ENV_FILE)" ]; then \
		if [ "$(origin CAMERA_USER)" = "command line" ]; then \
			bash deploy/deploy-camera.sh "$(CAMERA_ENV_FILE)" "$(CAMERA_USER)"; \
		else \
			bash deploy/deploy-camera.sh "$(CAMERA_ENV_FILE)"; \
		fi; \
	else \
		bash deploy/deploy-camera.sh "$(CAM)" "$(CAMERA_USER)"; \
	fi

deploy-base:
	@if [ -z "$(BASE)" ]; then echo "Usage: make deploy-base BASE=pi5.local BASE_USER=bostdiek"; exit 1; fi
	bash deploy/deploy-base.sh $(BASE) $(BASE_USER)

deploy-inference:
	@if [ -z "$(BASE)" ]; then echo "Usage: make deploy-inference BASE=pi5.local BASE_USER=bostdiek"; exit 1; fi
	bash deploy/deploy-inference.sh $(BASE) $(BASE_USER)

update-cameras:
	@for cam in $(CAMERAS); do \
		echo ">>> Deploying to $$cam..."; \
		rsync -avz --delete \
			packages/camera/src/piwatcher_camera \
			$(CAMERA_USER)@$$cam:$(CAMERA_DEST); \
		rsync -avz \
			packages/camera/.env.camera \
			$(CAMERA_USER)@$$cam:$(CAMERA_DEST).env; \
		ssh $(CAMERA_USER)@$$cam "sudo systemctl restart $(CAMERA_SERVICE)"; \
		echo ">>> $$cam updated."; \
	done

# First-time camera setup (run once per new Pi Zero)
setup-camera:
	@if [ -z "$(CAM)" ]; then echo "Usage: make setup-camera CAM=feeder-cam.local"; exit 1; fi
	ssh $(CAMERA_USER)@$(CAM) "mkdir -p ~/piwatcher/deploy"
	scp deploy/setup-camera.sh $(CAMERA_USER)@$(CAM):~/setup-camera.sh
	scp deploy/piwatcher-camera.service $(CAMERA_USER)@$(CAM):~/piwatcher/deploy/piwatcher-camera.service
	ssh $(CAMERA_USER)@$(CAM) "chmod +x ~/setup-camera.sh && sudo ~/setup-camera.sh"
