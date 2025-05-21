#!/usr/bin/env python3

import os
import sys
import yaml
import json
from typing import Dict, List, Any
import subprocess
from pathlib import Path
import time

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_gitlab_section(name: str, content: str):
    """Print a GitLab CI/CD section."""
    print(f"\n\033[0Ksection_start:{int(time.time())}:{name}\r\033[0K{content}")
    print(f"\033[0Ksection_end:{int(time.time())}:{name}\r\033[0K")

def print_gitlab_error(message: str):
    """Print a GitLab CI/CD error message."""
    print(f"\033[0K\033[31;1m{message}\033[0m")

def run_yamllint(file_path: str) -> bool:
    """Run yamllint on the given file."""
    try:
        result = subprocess.run(['yamllint', file_path], capture_output=True, text=True)
        if result.returncode != 0:
            print_gitlab_error(f"YAML Lint errors in {file_path}:")
            print(result.stdout)
            return False
        return True
    except subprocess.CalledProcessError as e:
        print_gitlab_error(f"Error running yamllint: {e}")
        return False

def validate_traefik_config(config: Dict[str, Any]) -> List[str]:
    """Validate Traefik configuration structure."""
    errors = []
    
    # Check if the file has any Traefik configuration
    if not any(key in config for key in ['http', 'tcp', 'udp']):
        errors.append("No Traefik configuration found (missing http, tcp, or udp sections)")
        return errors
    
    for section in ['http', 'tcp', 'udp']:
        if section in config:
            section_config = config[section]
            # If the section only contains 'middlewares', skip further checks
            section_keys = set(section_config.keys())
            if section_keys <= {'middlewares'}:
                continue
            routers = section_config.get('routers', {})
            # If routers exist, check if any reference a service (excluding @internal)
            if routers:
                references_noninternal_service = False
                for router in routers.values():
                    if isinstance(router, dict) and 'service' in router and router['service']:
                        service_val = router['service']
                        # Only require services section if not @internal
                        if not (isinstance(service_val, str) and service_val.endswith('@internal')):
                            references_noninternal_service = True
                            break
                if references_noninternal_service:
                    if 'services' not in section_config:
                        errors.append(f"Missing 'services' in {section.upper()} configuration, but at least one router references a non-internal service.")
            # Only require 'routers' if section contains 'services' or 'routers'
            if 'routers' not in section_config and ('services' in section_config or 'routers' in section_config):
                errors.append(f"Missing 'routers' in {section.upper()} configuration")
    
    return errors

def auto_correct_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Attempt to auto-correct common Traefik configuration issues."""
    corrected = config.copy()
    
    for section in ['http', 'tcp', 'udp']:
        if section in corrected:
            section_config = corrected[section]
            section_keys = set(section_config.keys())
            # If the section only contains 'middlewares', skip further corrections
            if section_keys <= {'middlewares'}:
                continue
            # Always ensure routers key exists if services or routers are present
            if ('services' in section_config or 'routers' in section_config) and 'routers' not in section_config:
                section_config['routers'] = {}
            routers = section_config.get('routers', {})
            # Only add services if routers reference a non-internal service
            references_noninternal_service = False
            for router in routers.values():
                if isinstance(router, dict) and 'service' in router and router['service']:
                    service_val = router['service']
                    if not (isinstance(service_val, str) and service_val.endswith('@internal')):
                        references_noninternal_service = True
                        break
            if references_noninternal_service and 'services' not in section_config:
                section_config['services'] = {}
    
    return corrected

def process_file(file_path: str, auto_correct: bool = False) -> bool:
    """Process a single Traefik configuration file."""
    print_gitlab_section(f"validate_{os.path.basename(file_path)}", f"Processing {file_path}...")
    
    # First run yamllint
    if not run_yamllint(file_path):
        return False
    
    # Read and parse YAML
    try:
        with open(file_path, 'r') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print_gitlab_error(f"Error parsing YAML: {e}")
        return False
    
    # Skip validation for non-Traefik YAML files
    if not any(key in config for key in ['http', 'tcp', 'udp']):
        print(f"{Colors.GREEN}✓{Colors.ENDC} {file_path} is valid (not a Traefik configuration file)")
        return True
    
    # Validate Traefik configuration
    errors = validate_traefik_config(config)
    if errors:
        print_gitlab_error(f"Validation errors in {file_path}:")
        for error in errors:
            print_gitlab_error(f"  - {error}")
        
        if auto_correct:
            print(f"\n{Colors.YELLOW}Attempting to auto-correct...{Colors.ENDC}")
            corrected_config = auto_correct_config(config)
            
            # Write corrected configuration
            with open(file_path, 'w') as f:
                yaml.dump(corrected_config, f, default_flow_style=False)
            print(f"{Colors.GREEN}Configuration has been auto-corrected.{Colors.ENDC}")
            return True
        return False
    
    print(f"{Colors.GREEN}✓{Colors.ENDC} {file_path} is valid")
    return True

def main():
    """Main function to process all Traefik configuration files."""
    if len(sys.argv) < 2:
        print("Usage: python validate_traefik.py [--auto-correct] <directory>")
        sys.exit(1)
    
    auto_correct = '--auto-correct' in sys.argv
    if auto_correct:
        sys.argv.remove('--auto-correct')
    
    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print_gitlab_error(f"Error: {directory} is not a directory")
        sys.exit(1)
    
    # Find all YAML files in the directory
    yaml_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(('.yml', '.yaml')):
                yaml_files.append(os.path.join(root, file))
    
    if not yaml_files:
        print(f"No YAML files found in {directory}")
        sys.exit(0)
    
    print_gitlab_section("validation_summary", f"{Colors.BOLD}Starting Traefik Configuration Validation{Colors.ENDC}")
    
    # Process each file
    success = True
    for file_path in yaml_files:
        if not process_file(file_path, auto_correct):
            success = False
    
    if success:
        print_gitlab_section("validation_result", f"{Colors.GREEN}✓ All files are valid!{Colors.ENDC}")
    else:
        print_gitlab_section("validation_result", f"{Colors.RED}✗ Some files have validation errors.{Colors.ENDC}")
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 
