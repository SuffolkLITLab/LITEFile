"""
Configuration Manager for Multi-State eFile System

This module provides centralized configuration management with inheritance support,
enabling different states and courts to customize forms while maintaining consistency.
"""

import logging
from copy import deepcopy
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Manages hierarchical configuration loading and merging for multi-state support.

    Features:
    - State-specific configuration inheritance from base templates
    - Court-specific requirement overlays
    - Configuration validation and caching
    """

    def __init__(self, config_dir=None):
        """
        Initialize the Configuration Manager.

        Args:
            config_dir (str, optional): Path to configuration directory.
                                       Defaults to static/config/
        """
        if config_dir is None:
            # Default to the config directory in static files
            base_dir = Path(__file__).parent.parent / "static" / "config"
        else:
            base_dir = Path(config_dir)

        self.config_dir = base_dir
        self.states_dir = base_dir / "states"
        self.base_config_file = base_dir / "base-case-types.yaml"

        # Cache for loaded configurations
        self._cache = {}

        # Ensure directories exist
        self.states_dir.mkdir(parents=True, exist_ok=True)

    def get_base_config(self):
        """Load and cache the base configuration."""
        cache_key = "base_config"

        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.base_config_file.exists():
            logger.error(f"Base configuration file not found: {self.base_config_file}")
            return {}

        try:
            with open(self.base_config_file) as f:
                base_config = yaml.safe_load(f) or {}

            self._cache[cache_key] = base_config
            return base_config

        except Exception as e:
            logger.error(f"Error loading base configuration: {str(e)}")
            return {}

    def get_state_config(self, state):
        """
        Load state-specific configuration with base inheritance.

        Args:
            state (str): State code (e.g., 'illinois', 'massachusetts')

        Returns:
            dict: Merged configuration with base inheritance applied
        """
        cache_key = f"state_{state}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Load base configuration first
        base_config = self.get_base_config()

        # Load state-specific configuration
        state_file = self.states_dir / f"{state}.yaml"
        if not state_file.exists():
            logger.warning(f"State configuration file not found: {state_file}")
            return base_config

        try:
            with open(state_file) as f:
                state_config = yaml.safe_load(f) or {}

            # Merge state config with base config
            merged_config = self._deep_merge(base_config, state_config)

            # Cache the result
            self._cache[cache_key] = merged_config

            return merged_config

        except Exception as e:
            logger.error(f"Error loading state configuration for {state}: {str(e)}")
            return base_config

    def get_case_type_config(self, state, case_type, court=None):
        """
        Get complete configuration for a specific case type in a state.

        Args:
            state (str): State code (e.g., 'illinois', 'massachusetts')
            case_type (str): Case type (e.g., 'name_change', 'divorce')
            court (str, optional): Specific court for court-specific requirements

        Returns:
            dict: Complete case type configuration with inheritance applied
        """
        state_config = self.get_state_config(state)

        if not state_config or "case_types" not in state_config:
            return None

        case_config = state_config["case_types"].get(case_type)
        if not case_config:
            return None

        # Apply court-specific requirements if specified
        if court and "court_specific_requirements" in state_config:
            court_requirements = state_config["court_specific_requirements"].get(court, {})
            if "case_types" in court_requirements and case_type in court_requirements["case_types"]:
                court_case_config = court_requirements["case_types"][case_type]
                case_config = self._deep_merge(case_config, court_case_config)

        return case_config

    def get_available_states(self):
        """
        Get list of available state configurations.

        Returns:
            list: List of available state codes
        """
        if not self.states_dir.exists():
            return []

        states = []
        for state_file in self.states_dir.glob("*.yaml"):
            state_code = state_file.stem
            states.append(state_code)

        return sorted(states)

    def validate_configuration(self, state, case_type):
        """
        Validate that a configuration is properly structured.

        Args:
            state (str): State code
            case_type (str): Case type

        Returns:
            dict: Validation results with any errors or warnings
        """
        validation_results = {"valid": True, "errors": [], "warnings": []}

        try:
            case_config = self.get_case_type_config(state, case_type)

            if not case_config:
                validation_results["valid"] = False
                validation_results["errors"].append(f"No configuration found for {state}:{case_type}")
                return validation_results

            # Check for required fields
            if "sections" not in case_config:
                validation_results["errors"].append("Missing 'sections' in case type configuration")
                validation_results["valid"] = False

        except Exception as e:
            validation_results["valid"] = False
            validation_results["errors"].append(f"Configuration validation error: {str(e)}")

        return validation_results

    def _deep_merge(self, base_dict, override_dict):
        """
        Deep merge two dictionaries with override precedence.

        Args:
            base_dict (dict): Base configuration
            override_dict (dict): Override configuration

        Returns:
            dict: Merged configuration
        """
        if not isinstance(base_dict, dict) or not isinstance(override_dict, dict):
            return override_dict

        result = deepcopy(base_dict)

        for key, value in override_dict.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)

        return result

    def clear_cache(self):
        """Clear the configuration cache."""
        self._cache.clear()
        logger.info("Configuration cache cleared")

    def get_cache_info(self):
        """Get information about cached configurations."""
        return {"cached_configs": list(self._cache.keys()), "cache_size": len(self._cache)}
