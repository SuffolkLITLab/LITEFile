"""
API views for dropdown data in Illinois eFile system
Handles cascading dropdowns for case categories, types, counties, etc.
Uses GET requests to external APIs exclusively.
"""

import logging

import requests
from django.views.decorators.http import require_http_methods

from ..utils.zip_to_county_il import get_county_by_zip
from .base import APIResponseMixin, get_auth_tokens

logger = logging.getLogger(__name__)


class DropdownAPIViews(APIResponseMixin):
    """API views for dropdown data"""

    @staticmethod
    @require_http_methods(["GET"])
    def get_case_categories(request):
        """Get available case categories from Suffolk LIT Lab API"""
        try:
            auth_tokens = get_auth_tokens(request)

            # Get required parameters
            court_code = request.GET.get("court")
            jurisdiction = request.GET.get("jurisdiction", "illinois")

            if not court_code:
                return DropdownAPIViews.error_response("Missing required court parameter")

            # Make API call to external categories endpoint
            api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/categories"

            # Make the API request with auth tokens if available
            headers = {}
            if auth_tokens and "token" in auth_tokens:
                headers["Authorization"] = f"Bearer {auth_tokens['token']}"

            logger.debug("GET %s header keys=%s", api_url, list(headers.keys()))
            response = requests.get(api_url, headers=headers, timeout=10)
            logger.debug(
                "Categories response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 200:
                # Parse the API response - expecting list of {name, code} objects
                api_data = response.json()

                # Transform API data to our dropdown format
                categories = []
                if isinstance(api_data, list):
                    for category in api_data:
                        if isinstance(category, dict) and "code" in category and "name" in category:
                            categories.append(
                                {"value": category["code"], "text": f"{category['name']} ({category['code']})"}
                            )

                return DropdownAPIViews.success_response(categories)
            else:
                return DropdownAPIViews.error_response(f"API request failed with status {response.status_code}")

        except (requests.RequestException, requests.Timeout) as api_error:
            logger.warning("Categories API request failed: %s", api_error)
            return DropdownAPIViews.error_response(f"API request failed: {str(api_error)}")
        except Exception as e:
            logger.exception("Unexpected error in get_case_categories")
            return DropdownAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def get_case_types(request):
        """Get case types based on selected category from Suffolk LIT Lab API"""
        try:
            auth_tokens = get_auth_tokens(request)

            # Get required parameters
            court_code = request.GET.get("court")
            category_id = request.GET.get("parent")  # category_id from case category dropdown
            jurisdiction = request.GET.get("jurisdiction", "illinois")

            if not court_code:
                return DropdownAPIViews.error_response("Missing required court parameter")

            if not category_id:
                return DropdownAPIViews.error_response("Missing required category_id parameter")

            # Make API call to external case types endpoint
            api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/case_types/?category_id={category_id}"

            # Make the API request with auth tokens if available
            headers = {}
            if auth_tokens and "token" in auth_tokens:
                headers["Authorization"] = f"Bearer {auth_tokens['token']}"

            logger.debug("GET %s header keys=%s", api_url, list(headers.keys()))
            response = requests.get(api_url, headers=headers, timeout=10)
            logger.debug(
                "Case types response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 200:
                # Parse the API response - expecting list of {name, code} objects
                api_data = response.json()

                # Transform API data to our dropdown format
                case_types = []
                if isinstance(api_data, list):
                    for case_type in api_data:
                        if isinstance(case_type, dict) and "code" in case_type and "name" in case_type:
                            case_types.append(
                                {"value": case_type["code"], "text": f"{case_type['name']} ({case_type['code']})"}
                            )

                return DropdownAPIViews.success_response(case_types)

        except Exception as e:
            logger.exception("Unexpected error in get_case_types")
    

    @staticmethod
    @require_http_methods(["GET"])
    def get_filing_types(request):
        """Get filing types based on selected case type from Suffolk LIT Lab API"""
        try:
            auth_tokens = get_auth_tokens(request)

            # Get required parameters
            court_code = request.GET.get("court")
            casetype_id = request.GET.get("parent")
            jurisdiction = request.GET.get("jurisdiction", "illinois")
            current_case_id = request.GET.get("current_case_id")

            # Set initial flag: True if no current case, False if there is a current case
            initial = "True" if not current_case_id else "False"

            if not court_code:
                return DropdownAPIViews.error_response("Missing required court parameter")

            if not casetype_id:
                return DropdownAPIViews.error_response("Missing required case type parameter")

            # Make API call to external filing types endpoint
            api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/filing_types/?initial={initial}&category_id={casetype_id}"

            # Make the API request with auth tokens if available
            headers = {}
            if auth_tokens and "token" in auth_tokens:
                headers["Authorization"] = f"Bearer {auth_tokens['token']}"

            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                # Parse the API response - expecting list of {name, code} objects
                api_data = response.json()

                # Transform API data to our dropdown format
                filing_types = []
                if isinstance(api_data, list):
                    for filing_type in api_data:
                        if isinstance(filing_type, dict) and "code" in filing_type and "name" in filing_type:
                            filing_types.append(
                                {"value": filing_type["code"], "text": f"{filing_type['name']} ({filing_type['code']})"}
                            )

                return DropdownAPIViews.success_response(filing_types)
            else:
                return DropdownAPIViews.error_response(f"API request failed with status {response.status_code}")

        except (requests.RequestException, requests.Timeout) as api_error:
            return DropdownAPIViews.error_response(f"API request failed: {str(api_error)}")
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def get_courts(request):
        """Get available courts based on user location/preferences"""
        try:
            auth_tokens = get_auth_tokens(request)

            jurisdiction = request.GET.get("jurisdiction", "illinois")
            user_zip = request.GET.get("user_zip")
            user_county = request.GET.get("user_county")

            # Make API call to external jurisdiction endpoint
            api_url = f"https://efile.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/?with_names=True"

            try:
                # Make the API request with auth tokens if available
                headers = {}
                if auth_tokens and "token" in auth_tokens:
                    headers["Authorization"] = f"Bearer {auth_tokens['token']}"

                logger.debug("GET %s header keys=%s", api_url, list(headers.keys()))
                logger.debug("GET %s header keys=%s", api_url, list(headers.keys()))
                response = requests.get(api_url, headers=headers, timeout=10)
                logger.debug(
                    "Optional services response: status=%s content_type=%s",
                    response.status_code,
                    response.headers.get("Content-Type"),
                )
                logger.debug(
                    "Courts response: status=%s content_type=%s",
                    response.status_code,
                    response.headers.get("Content-Type"),
                )

                if response.status_code == 200:
                    # Parse the API response - expecting list of {name, code} objects
                    api_data = response.json()

                    # Transform API data to our dropdown format
                    courts = []
                    if isinstance(api_data, list):
                        for court in api_data:
                            if isinstance(court, dict) and "code" in court and "name" in court:
                                # Filter out courts with unwanted patterns in the name
                                court_name = court["name"]
                                if any(pattern in court_name for pattern in ["(zOdyssey)", "z -", "zz"]):
                                    continue  # Skip this court

                                courts.append({"value": court["code"], "text": court["name"]})

                    # If we got courts from the API, return them with user location priority
                    if courts:
                        return DropdownAPIViews.success_response(
                            DropdownAPIViews._prioritize_courts_by_location(courts, user_zip, user_county)
                        )
                    else:
                        # If no courts found in API response, fall back to hardcoded data
                        raise requests.RequestException("No courts found in API response")

                else:
                    # API call failed, fall back to hardcoded Illinois courts
                    raise requests.RequestException(f"API returned status {response.status_code}")

            except (requests.RequestException, requests.Timeout):
                # Fallback to comprehensive Illinois courts if API fails
                logger.warning("Courts API failed; using fallback list")
                fallback_courts = [
                    {"value": "PSUPCRT", "text": "Supreme Court of Illinois"},
                    {"value": "PAC1", "text": "Appellate Court – 1st District"},
                    {"value": "PAC2", "text": "Appellate Court – 2nd District"},
                    {"value": "PAC3", "text": "Appellate Court – 3rd District"},
                    {"value": "PAC4", "text": "Appellate Court – 4th District"},
                    {"value": "PAC5", "text": "Appellate Court – 5th District"},
                    {"value": "ardc", "text": "ARDC Clerk's Office"},
                    {"value": "adams", "text": "Adams County"},
                    {"value": "alexander", "text": "Alexander County"},
                    {"value": "bond", "text": "Bond County"},
                    {"value": "boone", "text": "Boone County"},
                    {"value": "brown", "text": "Brown County"},
                    {"value": "bureau", "text": "Bureau County"},
                    {"value": "calhoun", "text": "Calhoun County"},
                    {"value": "carroll", "text": "Carroll County"},
                    {"value": "cass", "text": "Cass County"},
                    {"value": "champaign", "text": "Champaign County"},
                    {"value": "christian", "text": "Christian County"},
                    {"value": "clark", "text": "Clark County"},
                    {"value": "clay", "text": "Clay County"},
                    {"value": "clinton", "text": "Clinton County"},
                    {"value": "coles", "text": "Coles County"},
                    {"value": "cook:chd1", "text": "Cook County - Chancery - District 1 - Chicago"},
                    {"value": "cook:cd1", "text": "Cook County - County Division - District 1 - Chicago"},
                    {"value": "cook:crd1", "text": "Cook County - Criminal - District 1 - Chicago"},
                    {"value": "cook:dr1", "text": "Cook County - Domestic Relations - District 1 - Chicago"},
                    {"value": "cook:law1", "text": "Cook County - Law - District 1 - Chicago"},
                    {"value": "cook:cvd1", "text": "Cook County - Municipal Civil - District 1 - Chicago"},
                    {"value": "cook:pr1", "text": "Cook County - Probate - District 1 - Chicago"},
                    {"value": "crawford", "text": "Crawford County"},
                    {"value": "cumberland", "text": "Cumberland County"},
                    {"value": "dewitt", "text": "De Witt County"},
                    {"value": "dekalb", "text": "DeKalb County"},
                    {"value": "douglas", "text": "Douglas County"},
                    {"value": "dupage", "text": "DuPage County"},
                    {"value": "edgar", "text": "Edgar County"},
                    {"value": "edwards", "text": "Edwards County"},
                    {"value": "effingham", "text": "Effingham County"},
                    {"value": "fayette", "text": "Fayette County"},
                    {"value": "ford", "text": "Ford County"},
                    {"value": "franklin", "text": "Franklin County"},
                    {"value": "fulton", "text": "Fulton County"},
                    {"value": "gallatin", "text": "Gallatin County"},
                    {"value": "greene", "text": "Greene County"},
                    {"value": "grundy", "text": "Grundy County"},
                    {"value": "hamilton", "text": "Hamilton County"},
                    {"value": "hancock", "text": "Hancock County"},
                    {"value": "hardin", "text": "Hardin County"},
                    {"value": "henderson", "text": "Henderson County"},
                    {"value": "henry", "text": "Henry County"},
                    {"value": "iroquois", "text": "Iroquois County"},
                    {"value": "jackson", "text": "Jackson County"},
                    {"value": "jasper", "text": "Jasper County"},
                    {"value": "jefferson", "text": "Jefferson County"},
                    {"value": "jersey", "text": "Jersey County"},
                    {"value": "jodaviess", "text": "Jo Daviess County"},
                    {"value": "johnson", "text": "Johnson County"},
                    {"value": "kane", "text": "Kane County"},
                    {"value": "KankakeeCV", "text": "Kankakee - Civil"},
                    {"value": "KankakeeCR", "text": "Kankakee - Criminal"},
                    {"value": "KankakeeFAM", "text": "Kankakee - Family and Juvenile"},
                    {"value": "KankakeeTR", "text": "Kankakee - Traffic"},
                    {"value": "kendall", "text": "Kendall County"},
                    {"value": "knox", "text": "Knox County"},
                    {"value": "lasalle", "text": "LaSalle County"},
                    {"value": "lake", "text": "Lake County"},
                    {"value": "lawrence", "text": "Lawrence County"},
                    {"value": "lee", "text": "Lee County"},
                    {"value": "livingston", "text": "Livingston County"},
                    {"value": "logan", "text": "Logan County"},
                    {"value": "macon", "text": "Macon County"},
                    {"value": "macoupin", "text": "Macoupin County"},
                    {"value": "madison", "text": "Madison County"},
                    {"value": "marion", "text": "Marion County"},
                    {"value": "marshall", "text": "Marshall County"},
                    {"value": "mason", "text": "Mason County"},
                    {"value": "massac", "text": "Massac County"},
                    {"value": "mcdonough", "text": "McDonough County"},
                    {"value": "mchenry", "text": "McHenry County"},
                    {"value": "mclean", "text": "McLean County"},
                    {"value": "menard", "text": "Menard County"},
                    {"value": "mercer", "text": "Mercer County"},
                    {"value": "monroe", "text": "Monroe County"},
                    {"value": "montgomery", "text": "Montgomery County"},
                    {"value": "morgan", "text": "Morgan County"},
                    {"value": "moultrie", "text": "Moultrie County"},
                    {"value": "ogle", "text": "Ogle County"},
                    {"value": "peoria", "text": "Peoria County"},
                    {"value": "peoriacr", "text": "Peoria CR"},
                    {"value": "peoriacs", "text": "Peoria CS"},
                    {"value": "peoriatr", "text": "Peoria TR"},
                    {"value": "perry", "text": "Perry County"},
                    {"value": "piatt", "text": "Piatt County"},
                    {"value": "pike", "text": "Pike County"},
                    {"value": "pope", "text": "Pope County"},
                    {"value": "pulaski", "text": "Pulaski County"},
                    {"value": "putnam", "text": "Putnam County"},
                    {"value": "randolph", "text": "Randolph County"},
                    {"value": "richland", "text": "Richland County"},
                    {"value": "rockisland", "text": "Rock Island County"},
                    {"value": "saline", "text": "Saline County"},
                    {"value": "sangamon", "text": "Sangamon County"},
                    {"value": "schuyler", "text": "Schuyler County"},
                    {"value": "scott", "text": "Scott County"},
                    {"value": "shelby", "text": "Shelby County"},
                    {"value": "stclair", "text": "St. Clair County"},
                    {"value": "stark", "text": "Stark County"},
                    {"value": "stephenson", "text": "Stephenson County"},
                    {"value": "tazewell", "text": "Tazewell County"},
                    {"value": "tazewell:tr", "text": "Tazewell County - Traffic"},
                    {"value": "union", "text": "Union County"},
                    {"value": "vermilion", "text": "Vermilion County"},
                    {"value": "wabash", "text": "Wabash County"},
                    {"value": "warren", "text": "Warren County"},
                    {"value": "washington", "text": "Washington County"},
                    {"value": "wayne", "text": "Wayne County"},
                    {"value": "white", "text": "White County"},
                    {"value": "whiteside", "text": "Whiteside County"},
                    {"value": "will", "text": "Will County"},
                    {"value": "williamson", "text": "Williamson County"},
                    {"value": "woodford", "text": "Woodford County"},
                ]
                logger.debug("Returning fallback courts")
                return DropdownAPIViews.success_response(
                    DropdownAPIViews._prioritize_courts_by_location(fallback_courts, user_zip, user_county)
                )

        except Exception as e:
            logger.error("Error prioritizing courts by location: %s", str(e))
            return DropdownAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    def _prioritize_courts_by_location(courts, user_zip=None, user_county=None):
        """
        Prioritize courts based on user's location (zip code or county).
        Adds a 'default' flag to courts that match the user's location.
        """
        if not courts:
            return courts

        # Determine user county from zip code if provided
        target_county = user_county
        if user_zip and not target_county:
            target_county = get_county_by_zip(user_zip)

        if not target_county:
            return courts

        # Normalize county name for matching (lowercase, no spaces)
        target_county_normalized = target_county.lower().replace(" ", "").replace("county", "")

        # Create prioritized list
        prioritized_courts = []
        other_courts = []

        for court in courts:
            court_value = court.get("value", "").lower()
            court_text = court.get("text", "").lower()

            # Check if this court matches the user's county
            is_match = False

            # Direct value match (e.g., 'cook' matches 'cook')
            if court_value == target_county_normalized:
                is_match = True

            # Text match (e.g., 'Cook County' matches 'cook')
            elif target_county_normalized in court_text:
                is_match = True

            # Special handling for Cook County divisions
            elif target_county_normalized == "cook" and "cook:" in court_value:
                is_match = True

            if is_match:
                # Mark as default/recommended court with recommended text
                court_copy = court.copy()
                court_copy["text"] = f"{court['text']} (Recommended)"
                prioritized_courts.append(court_copy)
            else:
                other_courts.append(court)

        # Mark only the first prioritized court as selected/default
        final_courts = prioritized_courts + other_courts
        if prioritized_courts:
            # Mark the first recommended court as selected using multiple flag approaches
            final_courts[0]["selected"] = True
            final_courts[0]["default"] = True
            final_courts[0]["recommended"] = True
            final_courts[0]["isSelected"] = True  # Alternative property name

        return final_courts

    @staticmethod
    @require_http_methods(["GET"])
    def get_document_types(request):
        """Get document types based on selected filing type from Suffolk LIT Lab API"""
        try:
            auth_tokens = get_auth_tokens(request)

            # Get required parameters
            court_code = request.GET.get("court")
            filing_type_id = request.GET.get("parent")  # filing type ID from filing type dropdown
            jurisdiction = request.GET.get("jurisdiction", "illinois")

            if not court_code:
                return DropdownAPIViews.error_response("Missing required court parameter")

            if not filing_type_id:
                return DropdownAPIViews.error_response("Missing required filing type parameter")

            # Make API call to external document types endpoint
            api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/filing_types/{filing_type_id}/document_types"
            logger.debug("GET %s", api_url)

            # Make the API request with auth tokens if available
            headers = {}
            if auth_tokens and "token" in auth_tokens:
                headers["Authorization"] = f"Bearer {auth_tokens['token']}"

            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                # Parse the API response - expecting list of {name, code} objects
                api_data = response.json()

                # Transform API data to our dropdown format
                document_types = []
                if isinstance(api_data, list):
                    for document_type in api_data:
                        if isinstance(document_type, dict) and "code" in document_type and "name" in document_type:
                            document_types.append(
                                {
                                    "value": document_type["code"],
                                    "text": f"{document_type['name']} ({document_type['code']})",
                                }
                            )

                return DropdownAPIViews.success_response(document_types)
            else:
                return DropdownAPIViews.error_response(f"API request failed with status {response.status_code}")

        except (requests.RequestException, requests.Timeout) as api_error:
            return DropdownAPIViews.error_response(f"API request failed: {str(api_error)}")
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def get_optional_services(request):
        """Get optional services for a filing type from Suffolk LIT Lab API"""
        try:
            auth_tokens = get_auth_tokens(request)

            # Get required parameters
            court_code = request.GET.get("court")
            filing_type_id = request.GET.get("filing_type_id")
            jurisdiction = request.GET.get("jurisdiction", "illinois")

            if not court_code:
                return DropdownAPIViews.error_response("Missing required court parameter")

            if not filing_type_id:
                return DropdownAPIViews.error_response("Missing required filing_type_id parameter")

            # Make API call to Suffolk optional services endpoint
            api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/filing_types/{filing_type_id}/optional_services"

            try:
                # Make the API request with auth tokens if available
                headers = {}
                if auth_tokens and "token" in auth_tokens:
                    headers["Authorization"] = f"Bearer {auth_tokens['token']}"

                response = requests.get(api_url, headers=headers, timeout=10)

                if response.status_code == 200:
                    # Parse the API response - expecting list of service objects
                    api_data = response.json()

                    # Transform API data to our format
                    optional_services = []
                    if isinstance(api_data, list):
                        for service in api_data:
                            if isinstance(service, dict):
                                optional_services.append(
                                    {
                                        "code": service.get("code") or service.get("id"),
                                        "name": service.get("name") or service.get("label") or service.get("text"),
                                        "fee": service.get("fee") or service.get("cost") or 0,
                                        "description": service.get("description") or service.get("desc"),
                                        "required": service.get("required", False),
                                    }
                                )

                    return DropdownAPIViews.success_response(optional_services)

                else:
                    # API call failed, return empty list with info message
                    msg = (
                        "Optional services API returned status "
                        f"{response.status_code} for court {court_code}, "
                        f"filing type {filing_type_id}"
                    )
                    logger.info(msg)
                    return DropdownAPIViews.success_response([])

            except (requests.RequestException, requests.Timeout) as api_error:
                # Return empty list if API fails
                msg = (
                    "Optional services API request failed for court "
                    f"{court_code}, filing type {filing_type_id}: {api_error}"
                )
                logger.warning(msg)
                return DropdownAPIViews.success_response([])

        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def get_party_types(request):
        """Get available party types from Suffolk LIT Lab API based on case type"""
        try:
            auth_tokens = get_auth_tokens(request)

            # Get required parameters
            court_code = request.GET.get("court")
            case_type_code = request.GET.get("case_type")
            jurisdiction = request.GET.get("jurisdiction", "illinois")

            if not court_code or not case_type_code:
                return DropdownAPIViews.error_response("Missing required court or case_type parameters")

            # Make API call to external party types endpoint
            api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/case_types/{case_type_code}/party_types"

            # Make the API request with auth tokens if available
            headers = {}
            if auth_tokens and "token" in auth_tokens:
                headers["Authorization"] = f"Bearer {auth_tokens['token']}"

            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                # Parse the API response - expecting list of party type objects
                api_data = response.json()

                # Transform API data to our dropdown format
                party_types = []
                if isinstance(api_data, list):
                    for party_type in api_data:
                        if isinstance(party_type, dict) and "code" in party_type and "name" in party_type:
                            # Include all party types for now (no filtering)

                            party_types.append(
                                {
                                    "value": party_type["code"],
                                    "text": party_type["name"],
                                    "code": party_type["code"],
                                    "name": party_type["name"],
                                    "isRequired": party_type.get("isrequired", False),
                                    "isAvailableForNewParties": party_type.get("isAvailableForNewParties", True),
                                }
                            )

                    # Sort alphabetically by name
                    party_types.sort(key=lambda x: x["name"])

                return DropdownAPIViews.success_response(
                    {
                        "party_types": party_types,
                        "count": len(party_types),
                        "source": "suffolk_api",
                        "court": court_code,
                        "case_type": case_type_code,
                    }
                )
            else:
                # Log the error but don't expose sensitive details
                error_msg = f"External API returned status {response.status_code}"
                return DropdownAPIViews.error_response(error_msg)

        except requests.RequestException as e:
            logger.warning("Party types API request failed: %s", e)
            return DropdownAPIViews.error_response("Network error: Failed to fetch party types")
        except Exception as e:
            logger.exception("Unexpected error in get_party_types")
            return DropdownAPIViews.error_response(f"Unexpected error: {str(e)}")


# Individual view functions for URL mapping
get_case_categories = DropdownAPIViews.get_case_categories
get_case_types = DropdownAPIViews.get_case_types
get_filing_types = DropdownAPIViews.get_filing_types
get_courts = DropdownAPIViews.get_courts
get_document_types = DropdownAPIViews.get_document_types
get_optional_services = DropdownAPIViews.get_optional_services
get_party_types = DropdownAPIViews.get_party_types
