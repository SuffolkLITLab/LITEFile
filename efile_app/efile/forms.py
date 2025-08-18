from django import forms
from django.contrib.auth.models import User


class EFileLoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "id": "email", "required": True}))
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "password", "required": True})
    )


class EFileRegistrationForm(forms.Form):
    # Legal Name
    first_name = forms.CharField(
        max_length=100,
        label="First or Given Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'firstName', 'required': 'required'})
    )
    middle_name = forms.CharField(
        max_length=100, required=False, widget=forms.TextInput(attrs={"class": "form-control", "id": "middleName"})
    )
    last_name = forms.CharField(
        max_length=100,
        label="Last or Family Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'lastName', 'required': 'required'})
    )
    # Physical Address
    street_address = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "streetAddress", "required": "required"}),
    )
    street_address_2 = forms.CharField(
        max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control", "id": "streetAddress2"})
    )
    city = forms.CharField(
        max_length=100, widget=forms.TextInput(attrs={"class": "form-control", "id": "city", "required": "required"})
    )
    STATE_CHOICES = [
        ("", "Select a state"),
        ("AL", "Alabama"),
        ("AK", "Alaska"),
        ("AZ", "Arizona"),
        ("AR", "Arkansas"),
        ("CA", "California"),
        ("CO", "Colorado"),
        ("CT", "Connecticut"),
        ("DE", "Delaware"),
        ("FL", "Florida"),
        ("GA", "Georgia"),
        ("HI", "Hawaii"),
        ("ID", "Idaho"),
        ("IL", "Illinois"),
        ("IN", "Indiana"),
        ("IA", "Iowa"),
        ("KS", "Kansas"),
        ("KY", "Kentucky"),
        ("LA", "Louisiana"),
        ("ME", "Maine"),
        ("MD", "Maryland"),
        ("MA", "Massachusetts"),
        ("MI", "Michigan"),
        ("MN", "Minnesota"),
        ("MS", "Mississippi"),
        ("MO", "Missouri"),
        ("MT", "Montana"),
        ("NE", "Nebraska"),
        ("NV", "Nevada"),
        ("NH", "New Hampshire"),
        ("NJ", "New Jersey"),
        ("NM", "New Mexico"),
        ("NY", "New York"),
        ("NC", "North Carolina"),
        ("ND", "North Dakota"),
        ("OH", "Ohio"),
        ("OK", "Oklahoma"),
        ("OR", "Oregon"),
        ("PA", "Pennsylvania"),
        ("RI", "Rhode Island"),
        ("SC", "South Carolina"),
        ("SD", "South Dakota"),
        ("TN", "Tennessee"),
        ("TX", "Texas"),
        ("UT", "Utah"),
        ("VT", "Vermont"),
        ("VA", "Virginia"),
        ("WA", "Washington"),
        ("WV", "West Virginia"),
        ("WI", "Wisconsin"),
        ("WY", "Wyoming"),
    ]
    state = forms.ChoiceField(
        choices=STATE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select", "id": "state", "required": "required"}),
        label="State",
    )
    zip_code = forms.CharField(
        max_length=10, widget=forms.TextInput(attrs={"class": "form-control", "id": "zip", "required": "required"})
    )
    county = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "county",
                "autocomplete": "off",
                "placeholder": "Type or select county",
                "required": "required",
            }
        ),
        label="County",
    )
    # Contact Information
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'id': 'email',
            'label':'Email address for court communications',
            'required': 'required'})
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'label': 'Primary Phone Number',
            'id': 'phone',
            'required': 'required'
        })
    )
    # Password
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "password", "required": True})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "confirmPassword", "required": True})
    )
    COMM_CHOICES = [
        ("yes", "Yes, you may leave sensitive information in voicemail or text message."),
        ("no", "No, please do not leave sensitive information in voicemail or text messages."),
    ]

    commPreference = forms.ChoiceField(
        choices=COMM_CHOICES, widget=forms.RadioSelect, label="Communication Preference", required=True
    )

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_zip_code(self):
        zip_code = self.cleaned_data["zip_code"]
        import re

        if not re.match(r"^\d{5}(-\d{4})?$", zip_code):
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
            username=self.cleaned_data["email"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
        )
        return user

class EFileExpertForm(forms.Form):
    # Case Classification Fields
    court = forms.CharField(
        max_length=100,
        widget=forms.Select(attrs={
            'class': 'form-select dropdown-field',
            'id': 'court',
            'required': True
        })
    )
    case_category = forms.CharField(
        max_length=100,
        widget=forms.Select(attrs={
            'class': 'form-select dropdown-field',
            'id': 'case_category',
            'required': True
        })
    )
    case_type = forms.CharField(
        max_length=100,
        widget=forms.Select(attrs={
            'class': 'form-select dropdown-field',
            'id': 'case_type',
            'required': True
        })
    )
    filing_type = forms.CharField(
        max_length=100,
        widget=forms.Select(attrs={
            'class': 'form-select dropdown-field',
            'id': 'filing_type',
            'required': True
        })
    )
    document_type = forms.CharField(
        max_length=100,
        widget=forms.Select(attrs={
            'class': 'form-select dropdown-field',
            'id': 'document_type',
            'required': True
        })
    )
    
    # Petitioner Information (for name change cases)
    petitioner_first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'petitioner_first_name'
        })
    )
    petitioner_last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'petitioner_last_name'
        })
    )
    petitioner_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'id': 'petitioner_address',
            'rows': 3
        })
    )
    
    # Name Sought Information (for name change cases)
    new_first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'new_first_name'
        })
    )
    new_last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'new_last_name'
        })
    )
    
    # Optional Services (MultipleChoiceField for checkboxes)
    optional_services = forms.MultipleChoiceField(
        choices=[
            ('certified_mailing', 'Certified Mailing Fee (Each Mailing)'),
            ('record_search', 'Record Search'),
            ('copies_first', 'Copies - 1st Page'),
            ('mailing_fees', 'Mailing Fees (when clerk required to mail)'),
            ('copies_docket', 'Copies - Docket'),
            ('copies_2_19', 'Copies - Pages 2-19'),
            ('copies_20_beyond', 'Copies - Pages 20 and beyond'),
            ('certification_seal', 'Certification or Authentication with Seal'),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        case_type = cleaned_data.get('case_type', '')
        
        # If this is a name change case, make certain fields required
        if 'name change' in case_type.lower():
            if not cleaned_data.get('petitioner_first_name'):
                self.add_error('petitioner_first_name', 'This field is required for name change cases.')
            if not cleaned_data.get('petitioner_last_name'):
                self.add_error('petitioner_last_name', 'This field is required for name change cases.')
            if not cleaned_data.get('petitioner_address'):
                self.add_error('petitioner_address', 'This field is required for name change cases.')
            if not cleaned_data.get('new_first_name'):
                self.add_error('new_first_name', 'This field is required for name change cases.')
            if not cleaned_data.get('new_last_name'):
                self.add_error('new_last_name', 'This field is required for name change cases.')
                
        return cleaned_data
