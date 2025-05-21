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
    except FileNotFoundError:
        print_gitlab_error("yamllint not found. Please ensure it is installed and in your PATH.")
        return False

def validate_traefik_config(config: Dict[str, Any]) -> List[str]:
    """Validate Traefik configuration structure."""
    errors = []

    errors = []

    errors = []

    # If config is empty or None, it's not a Traefik file, no specific errors.
    if not config:
        return errors

    has_http_tcp_udp = any(key in config for key in ['http', 'tcp', 'udp'])
    has_entrypoints = 'entryPoints' in config

    if not has_http_tcp_udp and not has_entrypoints:
        errors.append("No Traefik configuration found (missing http, tcp, udp, or entryPoints sections)")
        return errors

    if not has_entrypoints or not isinstance(config.get('entryPoints'), dict) or not config['entryPoints']:
        # It's an error if there are other traefik sections (http, tcp, udp) OR if 'entryPoints' is present but invalid/empty.
        if has_http_tcp_udp or (has_entrypoints and (not isinstance(config.get('entryPoints'), dict) or not config['entryPoints'])) :
            errors.append("Missing or empty 'entryPoints' configuration.")
    
    # If only entryPoints is defined, and it's empty or invalid, it's effectively not a Traefik config.
    if has_entrypoints and not config['entryPoints'] and not has_http_tcp_udp and \
       ("Missing or empty 'entryPoints' configuration." in errors or not isinstance(config.get('entryPoints'),dict)):
        errors = ["No Traefik configuration found (missing http, tcp, udp, or entryPoints sections)"]
        return errors


    for section in ['http', 'tcp', 'udp']:
        if section in config:
            section_config = config[section]
            if not isinstance(section_config, dict):
                errors.append(f"Section '{section}' is not a valid dictionary.")
                continue

            # If the section only contains 'middlewares', skip further checks
            section_keys = set(section_config.keys())
            if section_keys <= {'middlewares'}:
                continue
            
            routers = section_config.get('routers', {})
            services = section_config.get('services', {})

            if not isinstance(routers, dict):
                errors.append(f"'routers' in section '{section}' is not a valid dictionary.")
                continue # Skip iterating router items if 'routers' itself is invalid
            
            for router_name, router_config in routers.items():
                if not isinstance(router_config, dict):
                    errors.append(f"Router '{router_name}' in {section.upper()} is not a valid dictionary.")
                    continue # Skip this router if it's invalid

                # Validate router rule
                rule = router_config.get('rule')
                # Rule is mandatory for HTTP and TCP routers
                if section in ['http', 'tcp']:
                    if not rule or not isinstance(rule, str) or not rule.strip():
                        errors.append(f"Router '{router_name}' in {section.upper()} has a missing, empty, or invalid rule.")
                # For UDP, if a rule is present, it must be a string.
                elif section == 'udp' and rule is not None and not isinstance(rule, str):
                    errors.append(f"Router '{router_name}' in {section.upper()} has an invalid rule type (must be a string).")
                elif rule and not isinstance(rule, str): # Catch-all for rule present but not string (if missed by above)
                     errors.append(f"Router '{router_name}' in {section.upper()} has an invalid rule type (must be a string).")
                # Placeholder for more complex rule syntax validation:
                # else:
                #   if section != 'udp' and not is_valid_rule_syntax(rule):
                #       errors.append(f"Router '{router_name}' in {section.upper()} has an invalid rule syntax: {rule}")

                # Validate service reference
                service_name = router_config.get('service')
                if service_name:
                    if not isinstance(service_name, str):
                        errors.append(f"Router '{router_name}' in {section.upper()} has an invalid service name type.")
                    elif not service_name.endswith('@internal') and service_name not in services:
                        errors.append(f"Router '{router_name}' in {section.upper()} references undefined service '{service_name}'.")

            # If routers exist, check if any reference a service (excluding @internal)
            if routers:
                references_noninternal_service = False
                for router in routers.values():
                    if isinstance(router, dict) and 'service' in router and router['service']:
                        service_val = router_config.get('service') # Use .get() for safety
                        # Only require services section if not @internal, and ensure services is a dict
                        if isinstance(service_val, str) and not service_val.endswith('@internal'):
                            references_noninternal_service = True
                            break
            
            if references_noninternal_service: # This check was outside the loop, needs to be at the correct indentation
                if 'services' not in section_config or not isinstance(section_config.get('services'), dict) or not section_config.get('services'):
                    errors.append(f"Missing or empty 'services' in {section.upper()} configuration, but at least one router references a non-internal service.")

            # Check if 'routers' key exists if 'services' key exists (and services is not empty)
            # This is a common pattern: if you define services, you usually have routers that use them.
            # However, middlewares-only files are an exception.
            if 'services' in section_config and section_config['services'] and 'routers' not in section_config:
                 if not (section_keys <= {'middlewares', 'services'}): # Allow if only middlewares and services defined
                    errors.append(f"Missing 'routers' in {section.upper()} configuration, but 'services' are defined.")

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
    except (IOError, OSError) as e:
        print_gitlab_error(f"Error reading file {file_path}: {e}")
        return False
    except yaml.YAMLError as e:
        print_gitlab_error(f"Error parsing YAML: {e}")
        return False
    
    # Skip validation for non-Traefik YAML files or empty files
    if not config or not any(key in config for key in ['http', 'tcp', 'udp', 'entryPoints']):
        if config and not any(key in config for key in ['http', 'tcp', 'udp', 'entryPoints']): # It has content, but not traefik
             print(f"{Colors.YELLOW}ⓘ{Colors.ENDC} {file_path} is valid (not a Traefik specific configuration file or empty)")
        else: # It's an empty file (config is None or empty dict)
             print(f"{Colors.GREEN}✓{Colors.ENDC} {file_path} is valid (empty file)")
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
            try:
                with open(file_path, 'w') as f:
                    yaml.dump(corrected_config, f, default_flow_style=False)
                print(f"{Colors.GREEN}Configuration has been auto-corrected.{Colors.ENDC}")
                return True
            except (IOError, OSError) as e:
                print_gitlab_error(f"Error writing file {file_path}: {e}")
                return False
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
