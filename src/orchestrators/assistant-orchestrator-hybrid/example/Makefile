define create_or_update_key_macos
	if [ -f $(1) ]; then \
		if grep -q "^$(2)=" $(1); then \
			sed -i '' "s~^$(2)=.*~$(2)=$$$(2)~" $(1); \
		else \
			echo "$(2)=$$$(2)" >> $(1); \
		fi; \
	else \
		echo "$(2)=$$$(2)" > $(1); \
	fi
endef

define create_or_update_key_bash
	if [ -f $(1) ]; then \
		if grep -q "^$(2)=" $(1); then \
			sed -i "s~^$(2)=.*~$(2)=$$$(2)~" $(1); \
		else \
			echo "$(2)=$$$(2)" >> $(1); \
		fi; \
	else \
		echo "$(2)=$$$(2)" > $(1); \
	fi
endef

.PHONY: all-up all-down \
		debug-ao-up debug-ao-down \
		debug-services-up debug-services-down \
		dependencies-up dependencies-down \
		copy-envs \
		test-agent-up test-agent-down \
		debug-test-agent-up debug-test-agent-down

all-up:
	@echo "Starting base all services..."
	@docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	up -d

all-down:
	@echo "Stopping base all services..."
	@docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	down

all-down-clean-images:
	@echo "Stopping base all services..."
	@docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	down
	@docker rmi demo-client:latest || true

debug-ao-up:
	@echo "Starting services..."
	@KONG_ALT=./kong/kong-debug-ao.yaml \
	docker compose \
	--profile with-services \
	up -d

debug-ao-down:
	@echo "Stopping services..."
	@docker compose \
	--profile with-services \
	down

debug-services-up:
	@echo "Starting services..."
	@KONG_ALT=./kong/kong-debug-services.yaml \
	docker compose \
	--profile with-ao-hybrid \
	up -d

debug-services-down:
	@echo "Stopping services..."
	@docker compose \
	--profile with-ao-hybrid \
	down

test-agent-up:
	@echo "Starting services..."
	@KONG_ALT=./kong/kong-test-agent.yaml \
	AO_ALT=conf/config-w-test-agent.yaml \
	docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	--profile with-test-agent \
	up -d

test-agent-down:
	@echo "Stopping services..."
	@docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	--profile with-test-agent \
	down

debug-test-agent-up:
	@echo "Starting services..."
	@KONG_ALT=./kong/kong-debug-test-agent.yaml \
	AO_ALT=conf/config-w-test-agent.yaml \
	docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	up -d

debug-test-agent-down:
	@echo "Stopping services..."
	@docker compose \
	--profile with-ao-hybrid \
	--profile with-services \
	down

dependencies-up:
	@echo "Starting services..."
	@docker compose up -d

dependencies-down:
	@echo "Stopping services..."
	@docker compose down

copy-envs:
	cp general.env.example general.env
	cp ao-hybrid.env.example ao-hybrid.env
	cp recipient.env.example recipient.env
	cp services.env.example services.env
	cp weather.env.example weather.env
	cp math.env.example math.env
	cp test-agent.env.example test-agent.env

# prompt-api-keys-macos:
#   This target prompts the user to enter API keys for various services used in the project,
#   and updates the corresponding environment files with the entered keys.
prompt-api-keys-macos:
	@echo "Please enter your TA_API_KEY:"
	@read -p "API Key: " TA_API_KEY && \
		$(call create_or_update_key_macos,general.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,math.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,recipient.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,weather.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,test-agent.env,TA_API_KEY)
	@echo "key changes saved"
# prompt-api-keys-bash:
#   This target prompts the user to enter API keys for various services used in the project,
#   and updates the corresponding environment files with the entered keys.
#	The key difference from macos is sed -i does not require '' after -i which is required in macos
prompt-api-keys-bash:
	@echo "Please enter your TA_API_KEY:"
	@read -p "API Key: " TA_API_KEY && \
		$(call create_or_update_key_bash,general.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,math.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,recipient.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,weather.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,test-agent.env,TA_API_KEY)
	@echo "key changes saved"

build-environments-macos:
	@echo "generating env files from examples"
	make copy-envs
	@echo "requesting keys"
	make prompt-api-keys-macos
	@echo "envs created and keys configured"
build-environments-bash:
	@echo "generating env files from examples"
	make copy-envs
	@echo "requesting keys"
	make prompt-api-keys-bash
	@echo "envs created and keys configured"

deploy-updated-code:
	@echo "clean up existing resources"
	make all-down-clean-images
	@echo "going to parent directory and running 'make all'"
	@cd ../../../.. && make all
	@echo "deploy all changes and restart all containers"
	make all-up
	@docker builder prune -a
	@echo "cleaned build cache"
build-full-example-system-macos:
	make build-environments-macos
	make all-up
build-full-example-system-bash:
	make build-environments-bash
	make all-up

remove-local-db:
	rm -f ./dynamo/data/shared-local-instance.db

remove-env-files:
	rm -f general.env
	rm -f ao-hybrid.env
	rm -f recipient.env
	rm -f services.env
	rm -f weather.env
	rm -f math.env
	rm -f test-agent.env

refresh-env-macos:
	make remove-env-files
	make copy-envs
	make remove-local-db
	make prompt-api-keys-macos
	make deploy-updated-code

refresh-env-bash:
	make remove-env-files
	make copy-envs
	make remove-local-db
	make prompt-api-keys-bash
	make deploy-updated-code
