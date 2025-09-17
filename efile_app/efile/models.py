# models.py - Optional extension to store additional user information
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import models

if TYPE_CHECKING:
    from django.db.models import Manager


class UserProfile(models.Model):
    """
    Extended user profile to store Illinois eFile registration information
    """

    # Django automatically provides 'objects' manager and 'DoesNotExist' exception
    if TYPE_CHECKING:
        objects: "Manager[UserProfile]"

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Name information (stored in User model: first_name, last_name)
    middle_name = models.CharField(max_length=100, blank=True)

    # Physical Address
    street_address = models.CharField(max_length=255)
    street_address_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, default="IL")  # State abbreviation
    zip_code = models.CharField(max_length=10)

    # Illinois Counties choices
    COUNTY_CHOICES = [
        ("adams", "Adams"),
        ("alexander", "Alexander"),
        ("bond", "Bond"),
        ("boone", "Boone"),
        ("brown", "Brown"),
        ("bureau", "Bureau"),
        ("calhoun", "Calhoun"),
        ("carroll", "Carroll"),
        ("cass", "Cass"),
        ("champaign", "Champaign"),
        ("christian", "Christian"),
        ("clark", "Clark"),
        ("clay", "Clay"),
        ("clinton", "Clinton"),
        ("coles", "Coles"),
        ("cook", "Cook"),
        ("crawford", "Crawford"),
        ("cumberland", "Cumberland"),
        ("dekalb", "DeKalb"),
        ("dewitt", "DeWitt"),
        ("douglas", "Douglas"),
        ("dupage", "DuPage"),
        ("edgar", "Edgar"),
        ("edwards", "Edwards"),
        ("effingham", "Effingham"),
        ("fayette", "Fayette"),
        ("ford", "Ford"),
        ("franklin", "Franklin"),
        ("fulton", "Fulton"),
        ("gallatin", "Gallatin"),
        ("greene", "Greene"),
        ("grundy", "Grundy"),
        ("hamilton", "Hamilton"),
        ("hancock", "Hancock"),
        ("hardin", "Hardin"),
        ("henderson", "Henderson"),
        ("henry", "Henry"),
        ("iroquois", "Iroquois"),
        ("jackson", "Jackson"),
        ("jasper", "Jasper"),
        ("jefferson", "Jefferson"),
        ("jersey", "Jersey"),
        ("jodaviess", "Jo Daviess"),
        ("johnson", "Johnson"),
        ("kane", "Kane"),
        ("kankakee", "Kankakee"),
        ("kendall", "Kendall"),
        ("knox", "Knox"),
        ("lake", "Lake"),
        ("lasalle", "LaSalle"),
        ("lawrence", "Lawrence"),
        ("lee", "Lee"),
        ("livingston", "Livingston"),
        ("logan", "Logan"),
        ("macon", "Macon"),
        ("macoupin", "Macoupin"),
        ("madison", "Madison"),
        ("marion", "Marion"),
        ("marshall", "Marshall"),
        ("mason", "Mason"),
        ("massac", "Massac"),
        ("mcdonough", "McDonough"),
        ("mchenry", "McHenry"),
        ("mclean", "McLean"),
        ("menard", "Menard"),
        ("mercer", "Mercer"),
        ("monroe", "Monroe"),
        ("montgomery", "Montgomery"),
        ("morgan", "Morgan"),
        ("moultrie", "Moultrie"),
        ("ogle", "Ogle"),
        ("peoria", "Peoria"),
        ("perry", "Perry"),
        ("piatt", "Piatt"),
        ("pike", "Pike"),
        ("pope", "Pope"),
        ("pulaski", "Pulaski"),
        ("putnam", "Putnam"),
        ("randolph", "Randolph"),
        ("richland", "Richland"),
        ("rock_island", "Rock Island"),
        ("saline", "Saline"),
        ("sangamon", "Sangamon"),
        ("schuyler", "Schuyler"),
        ("scott", "Scott"),
        ("shelby", "Shelby"),
        ("stark", "Stark"),
        ("stephenson", "Stephenson"),
        ("tazewell", "Tazewell"),
        ("union", "Union"),
        ("vermilion", "Vermilion"),
        ("wabash", "Wabash"),
        ("warren", "Warren"),
        ("washington", "Washington"),
        ("wayne", "Wayne"),
        ("white", "White"),
        ("whiteside", "Whiteside"),
        ("will", "Will"),
        ("williamson", "Williamson"),
        ("winnebago", "Winnebago"),
        ("woodford", "Woodford"),
    ]

    county = models.CharField(max_length=50, choices=COUNTY_CHOICES)

    # Contact Information (email stored in User model)
    phone = models.CharField(max_length=20, blank=True)

    # Communication Preferences
    email_updates = models.BooleanField(default=False)
    text_updates = models.BooleanField(default=False)

    # Extended Suffolk integration fields (added to support auth_views integration)
    suffolk_user_id = models.CharField(max_length=100, blank=True, null=True)
    tyler_token = models.TextField(blank=True, null=True)
    preferred_county = models.CharField(max_length=50, default="cook")

    # API Tokens for Suffolk integration
    suffolk_access_token = models.TextField(blank=True, null=True)
    suffolk_refresh_token = models.TextField(blank=True, null=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)

    # Additional preferences
    language = models.CharField(max_length=10, default="en")
    timezone = models.CharField(max_length=50, default="America/Chicago")
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)

    # Firm information
    firm_name = models.CharField(max_length=255, blank=True, null=True)
    firm_id = models.CharField(max_length=100, blank=True, null=True)
    bar_number = models.CharField(max_length=50, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_full_address(self):
        """Return formatted full address"""
        parts = [self.street_address, self.street_address_2, self.city]
        if self.zip_code:
            parts.append(f"IL {self.zip_code}")
        return ", ".join(filter(None, parts))

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.county} County"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


# Helper functions to support auth_views integration with existing User model
def get_user_suffolk_integration_status(user):
    """Check if user has Suffolk integration set up"""
    try:
        profile = user.userprofile
        return bool(profile.suffolk_user_id)
    except ObjectDoesNotExist:
        return False


def get_user_tyler_token(user):
    """Get Tyler token from user profile"""
    try:
        profile = user.userprofile
        return profile.tyler_token
    except ObjectDoesNotExist:
        return None


def get_user_preferred_county(user):
    """Get user's preferred county - dynamically determine from zip code if not set"""
    try:
        profile = user.userprofile

        # If county is already set, use it
        if profile.county:
            return profile.county

        # If no county but we have zip code, determine county from zip
        if profile.zip_code:
            from efile.utils.zip_to_county_il import get_county_by_zip

            county = get_county_by_zip(profile.zip_code)
            if county:
                # Update the profile with the determined county for future use
                profile.county = county.lower()
                profile.save()
                return profile.county

        # Return empty string if no county can be determined
        return ""
    except ObjectDoesNotExist:
        return ""


def get_user_address_data(user):
    """Get user's address data for auth_views compatibility"""
    try:
        profile = user.userprofile
        return {
            "address_line1": profile.street_address or "",
            "address_line2": profile.street_address_2 or "",
            "city": profile.city or "",
            "state": profile.state or "",
            "zip_code": profile.zip_code or "",
            "phone": profile.phone or "",
        }
    except ObjectDoesNotExist:
        return {
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "state": "",
            "zip_code": "",
            "phone": "",
        }


def get_user_firm_data(user):
    """Get user's firm data for auth_views compatibility"""
    try:
        profile = user.userprofile
        return {
            "firm_name": profile.firm_name or "",
            "firm_id": profile.firm_id or "",
            "bar_number": profile.bar_number or "",
        }
    except ObjectDoesNotExist:
        return {
            "firm_name": "",
            "firm_id": "",
            "bar_number": "",
        }


def update_user_county_from_zip(user):
    """Update user's county based on their zip code. Returns True if updated, False if not."""
    try:
        profile = user.userprofile
        if profile.zip_code and not profile.county:
            from efile.utils.zip_to_county_il import get_county_by_zip

            county = get_county_by_zip(profile.zip_code)
            if county:
                profile.county = county.lower()
                profile.save()
                return True
        return False
    except ObjectDoesNotExist:
        return False


def update_user_suffolk_data(user, auth_data, state):
    """Update user profile with Suffolk API data"""
    try:
        profile, created = UserProfile.objects.get_or_create(  # type: ignore[attr-defined]
            user=user,
            defaults={
                "street_address": "",
                "city": "",
                "state": "",
                "zip_code": "",
                "county": "",
            },
        )

        # Update Suffolk integration fields
        if "access_token" in auth_data:
            profile.suffolk_access_token = auth_data["access_token"]

        if "refresh_token" in auth_data:
            profile.suffolk_refresh_token = auth_data["refresh_token"]

        # Update Tyler token - handle different response formats
        if "tokens" in auth_data:
            tokens = auth_data["tokens"]
            # Try different Tyler token key formats
            tyler_token = (
                tokens.get(f"TYLER-TOKEN-{state.upper()}")
                or tokens.get(f"tyler_token_{state}")
                or tokens.get(f"tyler-token-{state}")
            )
            if tyler_token:
                profile.tyler_token = tyler_token
        elif f"tyler_token_{state}" in auth_data:
            profile.tyler_token = auth_data[f"tyler_token_{state}"]

        # Extract user data from Suffolk API response
        if "user" in auth_data:
            user_info = auth_data["user"]
            profile.suffolk_user_id = user_info.get("id", user_info.get("user_id", ""))

        if "firm" in auth_data:
            firm_info = auth_data["firm"]
            profile.firm_name = firm_info.get("name", firm_info.get("firm_name", ""))
            profile.firm_id = firm_info.get("id", firm_info.get("firm_id", ""))

        # Update address if provided
        if "address" in auth_data:
            address_info = auth_data["address"]
            if address_info.get("addressLine1") or address_info.get("line1"):
                profile.street_address = address_info.get("addressLine1", address_info.get("line1", ""))
            if address_info.get("addressLine2") or address_info.get("line2"):
                profile.street_address_2 = address_info.get("addressLine2", address_info.get("line2", ""))
            if address_info.get("city"):
                profile.city = address_info.get("city", "")
            if address_info.get("state") or address_info.get("stateAbbreviation"):
                profile.state = address_info.get("state", address_info.get("stateAbbreviation", "IL"))
            if address_info.get("zipCode") or address_info.get("zip"):
                zip_code = address_info.get("zipCode", address_info.get("zip", ""))
                profile.zip_code = zip_code

                # Set county - prioritize API county, then derive from zip code
                api_county = address_info.get("county")
                if api_county:
                    profile.county = api_county.lower()
                elif zip_code:
                    # Automatically set county based on zip code
                    from efile.utils.zip_to_county_il import get_county_by_zip

                    county = get_county_by_zip(zip_code)
                    if county:
                        profile.county = county.lower()  # Store county in lowercase

        profile.save()
        return profile

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception("Error updating user Suffolk data: %s", str(e))
        return None


# Monkey patch User model to add Suffolk integration methods for auth_views compatibility
def user_has_suffolk_integration(self):
    """Check if user has Suffolk integration"""
    return get_user_suffolk_integration_status(self)


def user_get_tyler_token(self):
    """Get Tyler token"""
    return get_user_tyler_token(self)


def user_get_preferred_county(self):
    """Get preferred county"""
    return get_user_preferred_county(self)


def user_get_address_data(self):
    """Get address data"""
    return get_user_address_data(self)


def user_get_firm_data(self):
    """Get firm data"""
    return get_user_firm_data(self)


# Add methods to User model
User.add_to_class("has_suffolk_integration", property(user_has_suffolk_integration))
User.add_to_class("tyler_token", property(user_get_tyler_token))
User.add_to_class("preferred_county", property(user_get_preferred_county))
User.add_to_class("address_data", property(user_get_address_data))
User.add_to_class("firm_data", property(user_get_firm_data))

# Add individual address/firm properties for direct access (like auth_views expects)
User.add_to_class("address_line1", property(lambda self: self.address_data["address_line1"]))
User.add_to_class("address_line2", property(lambda self: self.address_data["address_line2"]))
User.add_to_class("city", property(lambda self: self.address_data["city"]))
User.add_to_class("state", property(lambda self: self.address_data["state"]))
User.add_to_class("zip_code", property(lambda self: self.address_data["zip_code"]))
User.add_to_class("phone", property(lambda self: self.address_data["phone"]))
User.add_to_class("firm_name", property(lambda self: self.firm_data["firm_name"]))
User.add_to_class("firm_id", property(lambda self: self.firm_data["firm_id"]))
User.add_to_class("bar_number", property(lambda self: self.firm_data["bar_number"]))
User.add_to_class(
    "suffolk_user_id",
    property(lambda self: getattr(self.userprofile, "suffolk_user_id", "") if hasattr(self, "userprofile") else ""),
)


# If using this model, you would also update the registration form's save method:
"""
# Updated save method for EFileRegistrationForm in views.py:

def save(self):
    # Create user with the form data
    user = User.objects.create_user(
        username=self.cleaned_data['email'],  # Use email as username
        email=self.cleaned_data['email'],
        password=self.cleaned_data['password'],
        first_name=self.cleaned_data['first_name'],
        last_name=self.cleaned_data['last_name']
    )
    
    # Create user profile with additional information
    UserProfile.objects.create(
        user=user,
        middle_name=self.cleaned_data['middle_name'],
        street_address=self.cleaned_data['street_address'],
        street_address_2=self.cleaned_data['street_address_2'],
        city=self.cleaned_data['city'],
        zip_code=self.cleaned_data['zip_code'],
        county=self.cleaned_data['county'],
        phone=self.cleaned_data['phone'],
        email_updates=self.cleaned_data['email_updates'],
        text_updates=self.cleaned_data['text_updates'],
    )
    
    return user
"""

# Don't forget to run migrations if you add this model:
# python manage.py makemigrations
# python manage.py migrate
