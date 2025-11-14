from efile.utils.config_loader import JurisdictionConfigLoader


class TestJurisdictionConfigLoader:
    """Test suite for the Jurisdiction Config Loader."""

    def test_load_jurisdiction_config(self):
        loader = JurisdictionConfigLoader()
        assert loader.load_jurisdiction_config("illinois")["state"]["code"] == "IL"

    def test_get_available_states(self):
        loader = JurisdictionConfigLoader()
        assert loader.get_available_jurisdictions() == ["illinois", "massachusetts"]

    def test_get_case_type_config(self):
        loader = JurisdictionConfigLoader()
        general_name_change = loader.get_case_type_config("illinois", "name_change")
        assert len(general_name_change["validation_rules"]) == 2
        assert "field_modifications" not in general_name_change

        bond_name_change = loader.get_case_type_config("illinois", "name_change", court="bond")
        assert len(bond_name_change["validation_rules"]) == 2
        assert len(bond_name_change["field_modifications"]) == 2

    def test_get_case_type_mods_applied(self):
        loader = JurisdictionConfigLoader()
        bond_sections = loader.get_case_type_config("illinois", "name_change", court="bond")["sections"]
        assert bond_sections["parties"]["fields"][0]["conditional_requirements"]["hidden_for_courts"] == ["bond"]

    def test_get_case_type_config_keywords(self):
        loader = JurisdictionConfigLoader()
        name_change = loader.get_case_type_config("illinois", "name_change")
        for alt_name in ["name change", "name petition", "change of name"]:
            assert name_change == loader.get_case_type_config("illinois", alt_name)

    def test_validate_config(self):
        loader = JurisdictionConfigLoader()
        v = loader.validate_configuration("illinois", "name_change")
        assert v["valid"]
