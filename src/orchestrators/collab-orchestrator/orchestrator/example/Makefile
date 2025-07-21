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
		dependencies-up dependencies-down \
		copy-envs

all-up:
	@echo "Starting base all services..."
	@docker compose \
	--profile with-co \
	up -d

all-down:
	@echo "Stopping base all services..."
	@docker compose \
	--profile with-co \
	down

all-down-clean-images:
	@echo "Stopping base all services..."
	@docker compose \
	--profile with-co \
	down

dependencies-up:
	@echo "Starting services..."
	@docker compose up -d

dependencies-down:
	@echo "Stopping services..."
	@docker compose down

copy-envs:
	cp ../co.env.example ../co.env
	cp manager-agent.env.example manager-agent.env
	cp planning-agent.env.example planning-agent.env
	cp search-agent.env.example search-agent.env
	cp task-agent.env.example task-agent.env

# prompt-api-keys-macos:
#   This target prompts the user to enter API keys for various services used in the project,
#   and updates the corresponding environment files with the entered keys.
prompt-api-keys-macos:
	@echo "Please enter your TA_API_KEY:"
	@read -p "API Key: " TA_API_KEY && \
		$(call create_or_update_key_macos,manager-agent.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,planning-agent.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,search-agent.env,TA_API_KEY) && \
		$(call create_or_update_key_macos,task-agent.env,TA_API_KEY)
	@echo "key changes saved"
# prompt-api-keys-bash:
#   This target prompts the user to enter API keys for various services used in the project,
#   and updates the corresponding environment files with the entered keys.
#	The key difference from macos is sed -i does not require '' after -i which is required in macos
prompt-api-keys-bash:
	@echo "Please enter your TA_API_KEY:"
	@read -p "API Key: " TA_API_KEY && \
		$(call create_or_update_key_bash,manager-agent.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,planning-agent.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,search-agent.env,TA_API_KEY) && \
		$(call create_or_update_key_bash,task-agent.env,TA_API_KEY)
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
	rm -f ../co.env
	rm -f manager-agent.env
	rm -f planning-agent.env
	rm -f search-agent.env
	rm -f task-agent.env

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
