"""
Jurisdiction-aware configuration loader for case types and form structures
"""

import os

import yaml
from django.conf import settings


class JurisdictionConfigLoader:
    """Load and merge YAML configuration files based on jurisdiction"""

    def __init__(self):
        self.config_dir = os.path.join(settings.BASE_DIR, "efile", "static", "config")
        self.states_dir = os.path.join(self.config_dir, "states")
        self.base_config = self._load_base_config()

    def _load_base_config(self):
        """Load the base configuration file"""
        base_path = os.path.join(self.config_dir, "base-case-types.yaml")
        try:
            with open(base_path) as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    def load_jurisdiction_config(self, jurisdiction):
        """
        Load configuration for a specific jurisdiction, merging with base config

        Args:
            jurisdiction (str): The jurisdiction code (e.g., 'illinois', 'massachusetts')

        Returns:
            dict: Merged configuration
        """
        jurisdiction_file = f"{jurisdiction}.yaml"
        jurisdiction_path = os.path.join(self.states_dir, jurisdiction_file)

        try:
            with open(jurisdiction_path) as f:
                jurisdiction_config = yaml.safe_load(f)

            # Merge with base configuration
            return self._deep_merge(self.base_config.copy(), jurisdiction_config)

        except FileNotFoundError:
            # If jurisdiction file not found, return base config with warning
            print(f"Warning: Configuration file not found for {jurisdiction}, using base config")
            return self.base_config

    def _deep_merge(self, base, overlay):
        """
        Deep merge two dictionaries, with overlay taking precedence

        Args:
            base (dict): Base configuration
            overlay (dict): Configuration to overlay

        Returns:
            dict: Merged configuration
        """
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def get_case_type_config(self, jurisdiction, case_type):
        """
        Get configuration for a specific case type in a jurisdiction

        Args:
            jurisdiction (str): The jurisdiction code
            case_type (str): The case type identifier

        Returns:
            dict: Case type configuration or None if not found
        """
        config = self.load_jurisdiction_config(jurisdiction)

        # Look in jurisdiction-specific case types first
        if "case_types" in config and case_type in config["case_types"]:
            return config["case_types"][case_type]

        # Fall back to base case types
        if "base_case_types" in config and case_type in config["base_case_types"]:
            return config["base_case_types"][case_type]

        return None

    def get_party_types(self, jurisdiction, court=None, case_type=None):
        """
        Get available party types for a jurisdiction, optionally filtered by court/case type

        Args:
            jurisdiction (str): The jurisdiction code
            court (str, optional): Court identifier for filtering
            case_type (str, optional): Case type for filtering

        Returns:
            dict: Available party types
        """
        config = self.load_jurisdiction_config(jurisdiction)

        if "party_types" not in config:
            return {}

        party_types = config["party_types"]

        # Apply court-specific filtering if specified
        if court and "courts" in config and court in config["courts"]:
            court_config = config["courts"][court]
            if "allowed_party_types" in court_config:
                allowed_types = court_config["allowed_party_types"]
                party_types = {k: v for k, v in party_types.items() if k in allowed_types}

        # Apply case type filtering if specified
        if case_type:
            case_config = self.get_case_type_config(jurisdiction, case_type)
            if case_config and "allowed_party_types" in case_config:
                allowed_types = case_config["allowed_party_types"]
                party_types = {k: v for k, v in party_types.items() if k in allowed_types}

        return party_types


# Global instance
config_loader = JurisdictionConfigLoader()
