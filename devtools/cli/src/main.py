import argparse
import os
import sys
from pathlib import Path

def load_template(template_path: Path) -> str:
    with open(template_path, "r") as f:
        return f.read()

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"Created {path}")

def get_template_dir() -> Path:
    # Assuming templates are in ../templates relative to this script
    return Path(__file__).parent.parent / "templates"

def create_agent(args):
    print(f"Creating Agent: {args.name}")
    template_dir = get_template_dir() / "agent"
    target_dir = Path("agents") / args.name

    config_content = load_template(template_dir / "config.yaml")
    config_content = config_content.replace("{{name}}", args.name)
    config_content = config_content.replace("{{description}}", args.description or f"Agent {args.name}")
    config_content = config_content.replace("{{model}}", args.model)

    write_file(target_dir / "config.yaml", config_content)
    print(f"\nAgent {args.name} created at {target_dir}")
    print("To run this agent, ensure you point TA_SERVICE_CONFIG to this config file.")

def create_ao(args):
    print(f"Creating Assistant Orchestrator: {args.name}")
    template_dir = get_template_dir() / "ao"
    target_dir = Path("orchestrators") / args.name

    config_content = load_template(template_dir / "config.yaml")
    config_content = config_content.replace("{{name}}", args.name)
    config_content = config_content.replace("{{description}}", args.description or f"Assistant Orchestrator {args.name}")

    write_file(target_dir / "config.yaml", config_content)
    print(f"\nAssistant Orchestrator {args.name} created at {target_dir}")

def create_co(args):
    print(f"Creating Collab Orchestrator: {args.name}")
    template_dir = get_template_dir() / "co"
    target_dir = Path("orchestrators") / args.name

    config_content = load_template(template_dir / "config.yaml")
    config_content = config_content.replace("{{name}}", args.name)
    config_content = config_content.replace("{{description}}", args.description or f"Collab Orchestrator {args.name}")

    write_file(target_dir / "config.yaml", config_content)
    print(f"\nCollab Orchestrator {args.name} created at {target_dir}")

def create_wo(args):
    print(f"Creating Workflow Orchestrator: {args.name}")
    template_dir = get_template_dir() / "wo"
    target_dir = Path("workflows") / args.name

    config_content = load_template(template_dir / "config.yaml")
    config_content = config_content.replace("{{name}}", args.name)
    config_content = config_content.replace("{{description}}", args.description or f"Workflow {args.name}")

    workflow_content = load_template(template_dir / "workflow.py")

    write_file(target_dir / "config.yaml", config_content)
    write_file(target_dir / "workflow.py", workflow_content)
    print(f"\nWorkflow {args.name} created at {target_dir}")

def main():
    parser = argparse.ArgumentParser(description="Teal Agents CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Common arguments
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--description", help="Description of the service")

    # Create Agent
    parser_agent = subparsers.add_parser("create-agent", parents=[parent_parser], help="Create a new Agent")
    parser_agent.add_argument("name", help="Name of the agent")
    parser_agent.add_argument("--model", default="gpt-4o", help="Model to use (default: gpt-4o)")
    parser_agent.set_defaults(func=create_agent)

    # Create Assistant Orchestrator
    parser_ao = subparsers.add_parser("create-ao", parents=[parent_parser], help="Create a new Assistant Orchestrator")
    parser_ao.add_argument("name", help="Name of the orchestrator")
    parser_ao.set_defaults(func=create_ao)

    # Create Collab Orchestrator
    parser_co = subparsers.add_parser("create-co", parents=[parent_parser], help="Create a new Collab Orchestrator")
    parser_co.add_argument("name", help="Name of the orchestrator")
    parser_co.set_defaults(func=create_co)

    # Create Workflow Orchestrator
    parser_wo = subparsers.add_parser("create-wo", parents=[parent_parser], help="Create a new Workflow Orchestrator")
    parser_wo.add_argument("name", help="Name of the workflow")
    parser_wo.set_defaults(func=create_wo)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
