.PHONY: all teal-agents orchestrator services

all : | teal-agents orchestrator services

teal-agents :
	@echo "Building Teal Agents..."
	@docker build ${DOCKER_FLAGS} -t teal-agents:latest -f teal-agents.Dockerfile --progress=plain .

orchestrator :
	@echo "Building Orchestrators..."
	@docker build ${DOCKER_FLAGS} -t ao:latest -f ao.Dockerfile --progress=plain .
	@docker build ${DOCKER_FLAGS} -t co:latest -f co.Dockerfile --progress=plain .

services :
	@echo "Building Services..."
	@docker build ${DOCKER_FLAGS} -t ao-services:latest -f ao-services.Dockerfile --progress=plain .

clean:
	@echo "Cleaning up..."
	@docker rmi teal-agents:latest || true
	@docker rmi ao:latest || true
	@docker rmi ao-services:latest || true