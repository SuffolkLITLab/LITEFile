from django import forms
from django.contrib.auth.models import User

class EFileLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'id': 'email',
            'required': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'id': 'password',
            'required': True
        })
    )

class EFileRegistrationForm(forms.Form):
    # Legal Name
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'firstName'})
    )
    middle_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'middleName'})
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'lastName'})
    )
    # Physical Address
    street_address = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'streetAddress'})
    )
    street_address_2 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'streetAddress2'})
    )
    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'city'})
    )
    zip_code = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'zip'})
    )
    COUNTY_CHOICES = [
        ('', 'Type or select Counties'),
        ('adams', 'Adams'),
        ('alexander', 'Alexander'),
        ('bond', 'Bond'),
        ('boone', 'Boone'),
        ('brown', 'Brown'),
        ('bureau', 'Bureau'),
        ('calhoun', 'Calhoun'),
        ('carroll', 'Carroll'),
        ('cass', 'Cass'),
        ('champaign', 'Champaign'),
        ('christian', 'Christian'),
        ('clark', 'Clark'),
        ('clay', 'Clay'),
        ('clinton', 'Clinton'),
        ('coles', 'Coles'),
        ('cook', 'Cook'),
        ('crawford', 'Crawford'),
        ('cumberland', 'Cumberland'),
        ('dekalb', 'DeKalb'),
        ('dewitt', 'DeWitt'),
        ('douglas', 'Douglas'),
        ('dupage', 'DuPage'),
        ('edgar', 'Edgar'),
        ('edwards', 'Edwards'),
        ('effingham', 'Effingham'),
        ('fayette', 'Fayette'),
        ('ford', 'Ford'),
        ('franklin', 'Franklin'),
        ('fulton', 'Fulton'),
        ('gallatin', 'Gallatin'),
        ('greene', 'Greene'),
        ('grundy', 'Grundy'),
        ('hamilton', 'Hamilton'),
        ('hancock', 'Hancock'),
        ('hardin', 'Hardin'),
        ('henderson', 'Henderson'),
        ('henry', 'Henry'),
        ('iroquois', 'Iroquois'),
        ('jackson', 'Jackson'),
        ('jasper', 'Jasper'),
        ('jefferson', 'Jefferson'),
        ('jersey', 'Jersey'),
        ('jodaviess', 'Jo Daviess'),
        ('johnson', 'Johnson'),
        ('kane', 'Kane'),
        ('kankakee', 'Kankakee'),
        ('kendall', 'Kendall'),
        ('knox', 'Knox'),
        ('lake', 'Lake'),
        ('lasalle', 'LaSalle'),
        ('lawrence', 'Lawrence'),
        ('lee', 'Lee'),
        ('livingston', 'Livingston'),
        ('logan', 'Logan'),
        ('macon', 'Macon'),
        ('macoupin', 'Macoupin'),
        ('madison', 'Madison'),
        ('marion', 'Marion'),
        ('marshall', 'Marshall'),
        ('mason', 'Mason'),
        ('massac', 'Massac'),
        ('mcdonough', 'McDonough'),
        ('mchenry', 'McHenry'),
        ('mclean', 'McLean'),
        ('menard', 'Menard'),
        ('mercer', 'Mercer'),
        ('monroe', 'Monroe'),
        ('montgomery', 'Montgomery'),
        ('morgan', 'Morgan'),
        ('moultrie', 'Moultrie'),
        ('ogle', 'Ogle'),
        ('peoria', 'Peoria'),
        ('perry', 'Perry'),
        ('piatt', 'Piatt'),
        ('pike', 'Pike'),
        ('pope', 'Pope'),
        ('pulaski', 'Pulaski'),
        ('putnam', 'Putnam'),
        ('randolph', 'Randolph'),
        ('richland', 'Richland'),
        ('rock_island', 'Rock Island'),
        ('saline', 'Saline'),
        ('sangamon', 'Sangamon'),
        ('schuyler', 'Schuyler'),
        ('scott', 'Scott'),
        ('shelby', 'Shelby'),
        ('stark', 'Stark'),
        ('stephenson', 'Stephenson'),
        ('tazewell', 'Tazewell'),
        ('union', 'Union'),
        ('vermilion', 'Vermilion'),
        ('wabash', 'Wabash'),
        ('warren', 'Warren'),
        ('washington', 'Washington'),
        ('wayne', 'Wayne'),
        ('white', 'White'),
        ('whiteside', 'Whiteside'),
        ('will', 'Will'),
        ('williamson', 'Williamson'),
        ('winnebago', 'Winnebago'),
        ('woodford', 'Woodford'),
    ]
    county = forms.ChoiceField(
        choices=COUNTY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'county'})
    )
    # Contact Information
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'id': 'email'})
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'id': 'phone',
            'placeholder': 'Ex: (XXX) XXX-XXXX or XXXXXXXXXX'
        })
    )
    # Password
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'password'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'for∂m-control', 'id': 'confirmPassword'})
    )
    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email
    def clean_zip_code(self):
        zip_code = self.cleaned_data['zip_code']
        import re
        if not re.match(r'^\d{5}(-\d{4})?$', zip_code):
            raise forms.ValidationError("Please enter a valid ZIP code (e.g., 12345 or 12345-6789)")
        return zip_code
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password:
            if password != confirm_password:
                raise forms.ValidationError("Passwords don't match")
        if password:
            if len(password) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long")
        return cleaned_data
    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name']
        )
        return user
