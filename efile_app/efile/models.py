# models.py - Optional extension to store additional user information
from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """
    Extended user profile to store Illinois eFile registration information
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Name information (stored in User model: first_name, last_name)
    middle_name = models.CharField(max_length=100, blank=True)

    # Physical Address
    street_address = models.CharField(max_length=255)
    street_address_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10)

    tyler_user_id = models.CharField(max_length=100, blank=True, null=True)
    tyler_token = models.TextField(blank=True, null=True)

    # TODO(brycew): uncomment when https://github.com/SuffolkLITLab/EfileProxyServer/issues/334 is in
    # token_expires_at = models.DateTimeField(blank=True, null=True)

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

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.county} County"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


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
