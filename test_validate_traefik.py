import unittest
from unittest.mock import patch, mock_open
import sys
import os
import subprocess
import importlib

# Add the script's directory to the Python path to allow importing validate_traefik
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import validate_traefik

class TestValidateTraefikConfig(unittest.TestCase):

    def test_valid_config_basic(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {
                    "router1": {
                        "rule": "Host(`example.com`)",
                        "service": "service1"
                    }
                },
                "services": {
                    "service1": {
                        "loadBalancer": {"servers": [{"address": "http://localhost:8080"}]}
                    }
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertEqual(len(errors), 0, f"Expected no errors, but got: {errors}")

    def test_valid_config_with_middlewares_only(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "middlewares": {
                    "auth": {"basicAuth": {"users": ["test:test"]}}
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertEqual(len(errors), 0, f"Expected no errors, but got: {errors}")

    def test_valid_config_internal_service(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {
                    "router-api": {
                        "rule": "PathPrefix(`/api`)",
                        "service": "api@internal"
                    }
                }
                # No 'services' section needed for internal services
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertEqual(len(errors), 0, f"Expected no errors, but got: {errors}")

    def test_invalid_missing_entrypoints(self):
        config = {
            "http": {
                "routers": {"router1": {"rule": "Host(`example.com`)", "service": "service1"}},
                "services": {"service1": {"loadBalancer": {"servers": [{"address": "http://localhost:8080"}]}}}
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Missing or empty 'entryPoints' configuration.", errors)

    def test_invalid_empty_entrypoints_with_other_sections(self):
        # entryPoints is empty, but other sections are present.
        config = {"entryPoints": {}, "http": {"routers": {"r1": {"rule": "Host(`foo.com`)", "service": "s1"}}, "services":{"s1":{}}}}
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Missing or empty 'entryPoints' configuration.", errors)

    def test_invalid_only_empty_entrypoints(self):
        config_only_empty_entrypoints = {"entryPoints": {}} # Only entryPoints, and it's empty
        errors = validate_traefik.validate_traefik_config(config_only_empty_entrypoints)
        # If entryPoints is the *only* section and it's empty, it means no real config.
        self.assertIn("No Traefik configuration found (missing http, tcp, udp, or entryPoints sections)", errors)

    def test_invalid_entrypoints_not_dict_with_other_sections(self):
        config = {"entryPoints": "not-a-dict", "http": {"routers": {"r1": {"rule": "Host()", "service": "s1"}}, "services": {"s1":{}}}}
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Missing or empty 'entryPoints' configuration.", errors)
    
    def test_invalid_entrypoints_not_dict_alone(self):
        config = {"entryPoints": "not-a-dict"} 
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Missing or empty 'entryPoints' configuration.", errors)


    def test_invalid_router_missing_rule(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {"router1": {"service": "service1"}},
                "services": {"service1": {"loadBalancer": {"servers": [{"address": "http://localhost:8080"}]}}}
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP has a missing, empty, or invalid rule.", errors)

    def test_invalid_router_empty_rule(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {"router1": {"rule": "  ", "service": "service1"}},
                "services": {"service1": {"loadBalancer": {"servers": [{"address": "http://localhost:8080"}]}}}
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP has a missing, empty, or invalid rule.", errors)

    def test_invalid_router_invalid_rule_type(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {"router1": {"rule": 123, "service": "service1"}},
                "services": {"service1": {"loadBalancer": {"servers": [{"address": "http://localhost:8080"}]}}}
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP has a missing, empty, or invalid rule.", errors)

    def test_invalid_service_not_defined(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {"router1": {"rule": "Host(`example.com`)", "service": "service1"}}
                # Missing 'services' section
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP references undefined service 'service1'.", errors)
        self.assertIn("Missing or empty 'services' in HTTP configuration, but at least one router references a non-internal service.", errors)

    def test_valid_service_defined_in_different_section_not_allowed(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {"router1": {"rule": "Host(`example.com`)", "service": "service1"}}
            },
            "tcp": { # Service defined in TCP, not HTTP
                "services": {
                    "service1": {"loadBalancer": {"servers": [{"address": "localhost:8080"}]}}
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP references undefined service 'service1'.", errors)


    def test_invalid_service_name_type(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {
                    "router1": {
                        "rule": "Host(`example.com`)",
                        "service": ["service1"] # Invalid type
                    }
                },
                "services": {
                    "service1": {
                        "loadBalancer": {"servers": [{"address": "http://localhost:8080"}]}
                    }
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP has an invalid service name type.", errors)

    def test_no_traefik_config_found(self):
        config = {"some_other_yaml": {"key": "value"}} # Not a traefik config file
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("No Traefik configuration found (missing http, tcp, udp, or entryPoints sections)", errors)

    def test_empty_config_not_traefik(self):
        config = {} # Empty config
        errors = validate_traefik.validate_traefik_config(config)
        # An empty config does not have traefik keys, so it should not produce errors.
        # The main script handles this by printing "empty file".
        self.assertEqual(len(errors), 0, f"Expected no errors for empty config, but got: {errors}")


    def test_tcp_and_udp_sections_valid(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}, "mqtt": {"address": ":1883"}, "dns": {"address": ":53/udp"}},
            "tcp": {
                "routers": {
                    "tcp_router1": {
                        "rule": "HostSNI(`mqtt.example.com`)",
                        "service": "mqtt_service"
                    }
                },
                "services": {
                    "mqtt_service": {
                        "loadBalancer": {"servers": [{"address": "localhost:1883"}]}
                    }
                }
            },
            "udp": {
                "routers": {
                    "udp_router1": { # Rule is not mandatory for UDP
                        "service": "dns_service"
                    },
                    "udp_router2_with_rule":{
                        "rule": "HostSNI(`dns.example.com`)", # Invalid for UDP, but rule syntax itself is not checked here
                        "service": "dns_service"
                    }
                },
                "services": {
                    "dns_service": {
                        "loadBalancer": {"servers": [{"address": "1.1.1.1:53"}]}
                    }
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertEqual(len(errors), 0, f"Expected no errors for TCP/UDP, but got: {errors}")

    def test_invalid_router_rule_type_for_udp_if_present(self):
        config = {
            "entryPoints": {"dns": {"address": ":53/udp"}},
            "udp": {
                "routers": {
                    "udp_router_invalid_rule":{
                        "rule": 12345, # Invalid type
                        "service": "dns_service"
                    }
                },
                "services": {
                    "dns_service": {"loadBalancer": {"servers": [{"address": "1.1.1.1:53"}]}}
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'udp_router_invalid_rule' in UDP has an invalid rule type (must be a string).", errors)


    def test_invalid_section_not_dictionary(self):
        config = {"entryPoints": {"web": ":80"}, "http": "this should be a dict"}
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Section 'http' is not a valid dictionary.", errors)

    def test_invalid_routers_not_dictionary(self):
        config = {"entryPoints": {"web": ":80"}, "http": {"routers": "this should be a dict"}}
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("'routers' in section 'http' is not a valid dictionary.", errors)


    def test_invalid_router_not_a_dictionary(self):
        config = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {
                "routers": {
                    "router1": "not-a-dict"
                }
            }
        }
        errors = validate_traefik.validate_traefik_config(config)
        self.assertIn("Router 'router1' in HTTP is not a valid dictionary.", errors)


class TestProcessFile(unittest.TestCase):

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    @patch('validate_traefik.validate_traefik_config')
    @patch('yaml.dump') # For auto-correct mock
    def test_process_file_valid(self, mock_yaml_dump, mock_validate_config, mock_yaml_load, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        mock_yaml_load.return_value = {
            "entryPoints": {"web": {"address": ":80"}},
            "http": {"routers": {"r1": {"rule": "Host(`foo.com`)", "service": "s1"}}, "services": {"s1": {}}}
        }
        mock_validate_config.return_value = [] # No errors

        result = validate_traefik.process_file("dummy/path/valid.yml")
        self.assertTrue(result)
        mock_open_file.assert_called_once_with("dummy/path/valid.yml", 'r')
        mock_yaml_load.assert_called_once()
        mock_validate_config.assert_called_once_with(mock_yaml_load.return_value)
        mock_yaml_dump.assert_not_called() # Auto-correct should not be called

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    @patch('validate_traefik.validate_traefik_config')
    def test_process_file_invalid_yaml(self, mock_validate_config, mock_yaml_load, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        mock_yaml_load.side_effect = validate_traefik.yaml.YAMLError("bad yaml")

        result = validate_traefik.process_file("dummy/path/invalid_yaml.yml")
        self.assertFalse(result)
        mock_open_file.assert_called_once_with("dummy/path/invalid_yaml.yml", 'r')
        mock_validate_config.assert_not_called()

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    @patch('validate_traefik.validate_traefik_config')
    def test_process_file_validation_error(self, mock_validate_config, mock_yaml_load, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        # This config will pass the "any traefik keys" check, but fail specific validation.
        mock_yaml_load.return_value = {"entryPoints": {"web": ":80"}, "http": {"routers": {"r1": {"service": "s1"}}}}
        mock_validate_config.return_value = ["Router 'r1' in HTTP has a missing, empty, or invalid rule."] # Validation error

        result = validate_traefik.process_file("dummy/path/invalid_traefik.yml")
        self.assertFalse(result)
        mock_validate_config.assert_called_once()

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    def test_process_file_not_traefik_config(self, mock_yaml_load, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        mock_yaml_load.return_value = {"not_traefik": "data"} # Not a traefik file

        result = validate_traefik.process_file("dummy/path/not_traefik.yml")
        self.assertTrue(result) # Should be considered valid as it's not a traefik file
        mock_open_file.assert_called_once_with("dummy/path/not_traefik.yml", 'r')

    @patch('validate_traefik.run_yamllint')
    def test_process_file_yamllint_fails(self, mock_run_yamllint):
        mock_run_yamllint.return_value = False # yamllint found errors

        result = validate_traefik.process_file("dummy/path/yamllint_error.yml")
        self.assertFalse(result)
        mock_run_yamllint.assert_called_once_with("dummy/path/yamllint_error.yml")

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    @patch('validate_traefik.validate_traefik_config')
    @patch('validate_traefik.auto_correct_config')
    @patch('yaml.dump')
    def test_process_file_autocorrect_success(self, mock_yaml_dump, mock_auto_correct, mock_validate_config, mock_yaml_load, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        initial_config_str = "entryPoints:\n  web: {}\nhttp:\n  routers:\n    r1:\n      rule: Host(`foo.com`)\n"
        initial_config_dict = {"entryPoints": {"web": {}}, "http": {"routers": {"r1": {"rule": "Host(`foo.com`)"}}}}
        corrected_config_dict = {"entryPoints": {"web": {}}, "http": {"routers": {"r1": {"rule": "Host(`foo.com`)"}}, "services": {}}}
        
        mock_yaml_load.return_value = initial_config_dict
        mock_validate_config.return_value = ["Missing 'services' section"]
        mock_auto_correct.return_value = corrected_config_dict

        # Capture the file handle used by the 'w' open call
        write_file_handle = mock_open().return_value
        mock_open_file.side_effect = [
            mock_open(read_data=initial_config_str).return_value, # For 'r'
            write_file_handle  # For 'w'
        ]

        result = validate_traefik.process_file("dummy/path/autocorrect_me.yml", auto_correct=True)
        self.assertTrue(result)
        mock_validate_config.assert_called_once_with(initial_config_dict)
        mock_auto_correct.assert_called_once_with(initial_config_dict)
        mock_yaml_dump.assert_called_once_with(corrected_config_dict, write_file_handle, default_flow_style=False)
        self.assertEqual(mock_open_file.call_count, 2)
        mock_open_file.assert_any_call("dummy/path/autocorrect_me.yml", 'r')
        mock_open_file.assert_any_call("dummy/path/autocorrect_me.yml", 'w')

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', side_effect=IOError("File not found"))
    def test_process_file_io_error_read(self, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        result = validate_traefik.process_file("dummy/path/nonexistent.yml")
        self.assertFalse(result)
        mock_open_file.assert_called_once_with("dummy/path/nonexistent.yml", 'r')

    @patch('validate_traefik.run_yamllint')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    @patch('validate_traefik.validate_traefik_config')
    @patch('validate_traefik.auto_correct_config')
    @patch('yaml.dump', side_effect=IOError("Cannot write"))
    def test_process_file_io_error_write_autocorrect(self, mock_yaml_dump, mock_auto_correct, mock_validate_config, mock_yaml_load, mock_open_file, mock_run_yamllint):
        mock_run_yamllint.return_value = True
        initial_config_str = "entryPoints:\n  web: {}\nhttp:\n  routers:\n    r1:\n      rule: Host(`foo.com`)\n"
        initial_config_dict = {"entryPoints": {"web": {}}, "http": {"routers": {"r1": {"rule": "Host(`foo.com`)"}}}}
        corrected_config_dict = {"entryPoints": {"web": {}}, "http": {"routers": {"r1": {"rule": "Host(`foo.com`)"}}, "services": {}}}
        
        mock_yaml_load.return_value = initial_config_dict
        mock_validate_config.return_value = ["Missing 'services' section"]
        mock_auto_correct.return_value = corrected_config_dict

        # Capture the file handle for the 'w' call
        write_file_handle = mock_open().return_value
        mock_open_file.side_effect = [
            mock_open(read_data=initial_config_str).return_value, # For 'r'
            write_file_handle  # For 'w'
        ]
        
        result = validate_traefik.process_file("dummy/path/autocorrect_fail_write.yml", auto_correct=True)
        self.assertFalse(result) # Expect False because yaml.dump raises IOError
        mock_yaml_dump.assert_called_once_with(corrected_config_dict, write_file_handle, default_flow_style=False)

# Removed duplicate class TestMainFunction(unittest.TestCase):

class TestRunYamllint(unittest.TestCase):
    @patch('subprocess.run')
    def test_run_yamllint_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Success"
        result = validate_traefik.run_yamllint("valid.yaml")
        self.assertTrue(result)
        mock_subprocess_run.assert_called_once_with(['yamllint', 'valid.yaml'], capture_output=True, text=True)

    @patch('subprocess.run')
    def test_run_yamllint_failure(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stdout = "Error: ..."
        result = validate_traefik.run_yamllint("invalid.yaml")
        self.assertFalse(result)

    @patch('subprocess.run', side_effect=FileNotFoundError)
    def test_run_yamllint_not_found(self, mock_subprocess_run):
        result = validate_traefik.run_yamllint("any.yaml")
        self.assertFalse(result)
        # Check if print_gitlab_error was called (indirectly, by checking output or mocking print)
        # For simplicity, we'll trust the script's print_gitlab_error handles output

    @patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, "cmd"))
    def test_run_yamllint_called_process_error(self, mock_subprocess_run):
        result = validate_traefik.run_yamllint("any.yaml")
        self.assertFalse(result)


class TestMainFunction(unittest.TestCase):

    def setUp(self):
        # Ensure sys.exit is patched for each test method in this class
        # to avoid interference between tests.
        patcher = patch('sys.exit')
        self.mock_sys_exit = patcher.start()
        self.addCleanup(patcher.stop)

    @patch('os.path.isdir', return_value=True)
    @patch('os.walk')
    @patch('validate_traefik.run_yamllint') # Ensure yamllint is mocked for calls from main->process_file
    @patch('validate_traefik.process_file')
    def test_main_valid_directory_all_files_valid(self, mock_process_file, mock_run_yamllint, mock_os_walk, mock_os_path_isdir):
        mock_run_yamllint.return_value = True # Assume yamllint passes for these tests
        self.mock_sys_exit.reset_mock()
        original_argv = sys.argv.copy()
        sys.argv = ['validate_traefik.py', 'dummy_dir']
        try:
            mock_os_walk.return_value = [
                ('/dummy_dir', [], ['file1.yml', 'file2.yaml']),
                ('/dummy_dir/subdir', [], ['file3.yml'])
            ]
            mock_process_file.return_value = True
            validate_traefik.main()

            self.assertEqual(mock_process_file.call_count, 3)
            mock_process_file.assert_any_call(os.path.join('/dummy_dir', 'file1.yml'), False)
            mock_process_file.assert_any_call(os.path.join('/dummy_dir', 'file2.yaml'), False)
            mock_process_file.assert_any_call(os.path.join('/dummy_dir/subdir', 'file3.yml'), False)
            self.mock_sys_exit.assert_called_once_with(0)
        finally:
            sys.argv = original_argv

    @patch('os.path.isdir', return_value=True)
    @patch('os.walk')
    @patch('validate_traefik.run_yamllint')
    @patch('validate_traefik.process_file')
    def test_main_autocorrect_enabled(self, mock_process_file, mock_run_yamllint, mock_os_walk, mock_os_path_isdir):
        mock_run_yamllint.return_value = True
        self.mock_sys_exit.reset_mock()
        original_argv = sys.argv.copy()
        sys.argv = ['validate_traefik.py', '--auto-correct', 'dummy_dir']
        try:
            mock_os_walk.return_value = [('/dummy_dir', [], ['file1.yml'])]
            mock_process_file.return_value = True # This line was misplaced
            validate_traefik.main()
            mock_process_file.assert_called_once_with(os.path.join('/dummy_dir', 'file1.yml'), True)
            self.mock_sys_exit.assert_called_once_with(0)
        finally:
            sys.argv = original_argv

    @patch('os.path.isdir', return_value=True)
    @patch('os.walk')
    @patch('validate_traefik.run_yamllint')
    @patch('validate_traefik.process_file')
    def test_main_some_files_invalid(self, mock_process_file, mock_run_yamllint, mock_os_walk, mock_os_path_isdir):
        mock_run_yamllint.return_value = True
        self.mock_sys_exit.reset_mock()
        original_argv = sys.argv.copy()
        sys.argv = ['validate_traefik.py', 'dummy_dir']
        try:
            mock_os_walk.return_value = [('/dummy_dir', [], ['file1.yml', 'file2.yml'])]
            mock_process_file.side_effect = [True, False]
            validate_traefik.main()
            self.assertEqual(mock_process_file.call_count, 2)
            self.mock_sys_exit.assert_called_once_with(1)
        finally:
            sys.argv = original_argv

    @patch('os.path.isdir', return_value=False)
    @patch('validate_traefik.print_gitlab_error')
    def test_main_invalid_directory(self, mock_print_error, mock_os_path_isdir):
        # No need to mock process_file or run_yamllint here as main should exit before calling them.
        importlib.reload(validate_traefik) # Keep reload for main tests for now
        self.mock_sys_exit.reset_mock()
        original_argv = sys.argv.copy()
        sys.argv = ['validate_traefik.py', 'non_existent_dir']
        try:
            validate_traefik.main()
            mock_os_path_isdir.assert_called_once_with('non_existent_dir')
            mock_print_error.assert_called_once_with("Error: non_existent_dir is not a directory")
            self.mock_sys_exit.assert_called_once_with(1)
        finally:
            sys.argv = original_argv

    @patch('builtins.print')
    def test_main_no_directory_arg(self, mock_print):
        importlib.reload(validate_traefik)
        self.mock_sys_exit.reset_mock()
        original_argv = sys.argv.copy()
        sys.argv = ['validate_traefik.py']
        try:
            validate_traefik.main() 
            mock_print.assert_any_call("Usage: python validate_traefik.py [--auto-correct] <directory>")
            self.mock_sys_exit.assert_called_once_with(1)
        finally:
            sys.argv = original_argv

    @patch('os.path.isdir', return_value=True)
    @patch('os.walk', return_value=[])
    @patch('builtins.print')
    def test_main_no_yaml_files_found(self, mock_print, mock_os_walk, mock_os_path_isdir):
        # No need to mock process_file or run_yamllint here
        importlib.reload(validate_traefik)
        self.mock_sys_exit.reset_mock()
        original_argv = sys.argv.copy()
        sys.argv = ['validate_traefik.py', 'dummy_dir']
        try:
            validate_traefik.main()
            mock_print.assert_any_call("No YAML files found in dummy_dir")
            self.mock_sys_exit.assert_called_once_with(0)
        finally:
            sys.argv = original_argv


if __name__ == '__main__':
    unittest.main()
