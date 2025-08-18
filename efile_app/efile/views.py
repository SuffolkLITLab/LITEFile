# views.py - Complete updated file for Illinois eFile system
from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .utils.case_config import case_types_config
import json

# Preserving original imports for when we un-comment all the other methods.
# from django.contrib.auth import authenticate, login
# from django.views.generic import TemplateView
# from .forms import EFileLoginForm, EFileRegistrationForm
# from django.contrib.auth.models import User

# Login view (simplified - no longer handles registration)
# def efile_login(request):
#     """
#     Handle login and redirect to separate registration page
#     """
#     login_form = EFileLoginForm()

#     if request.method == 'POST':
#         if 'login_submit' in request.POST:
#             # Handle login
#             login_form = EFileLoginForm(request.POST)
#             if login_form.is_valid():
#                 email = login_form.cleaned_data['email']
#                 password = login_form.cleaned_data['password']

#                 # Try to find user by email
#                 try:
#                     user = User.objects.get(email=email)
#                     user = authenticate(request, username=user.username, password=password)
#                     if user is not None:
#                         login(request, user)
#                         messages.success(request, 'Successfully logged in!')
#                         # Redirect to next page if specified, otherwise dashboard
#                         next_page = request.GET.get('next', 'dashboard')
#                         return redirect(next_page)
#                     else:
#                         messages.error(request, 'Invalid email or password.')
#                 except User.DoesNotExist:
#                     messages.error(request, 'No account found with this email address.')

#     context = {
#         'login_form': login_form,
#     }
#     return render(request, 'efile/login.html', context)

# # New separate registration view
# def efile_register(request):
#     import requests
#     if request.method == 'POST':
#         form = EFileRegistrationForm(request.POST)
#         if form.is_valid():
#             # Prepare payload for external API
#             data = {
#                 "registrationType": "INDIVIDUAL",
#                 "firstName": form.cleaned_data["first_name"],
#                 "middleName": form.cleaned_data.get("middle_name", ""),
#                 "lastName": form.cleaned_data["last_name"],
#                 "streetAddressLine1": form.cleaned_data["street_address"],
#                 "streetAddressLine2": form.cleaned_data.get("street_address_2", ""),
#                 "city": form.cleaned_data["city"],
#                 "state": form.cleaned_data["state"],
#                 "zipCode": form.cleaned_data["zip_code"],
#                 "countryCode": "US",
#                 "county": form.cleaned_data["county"],
#                 "email": form.cleaned_data["email"],
#                 "phoneNumber": form.cleaned_data.get("phone", ""),
#                 # "emailUpdates": form.cleaned_data.get("email_updates", False),
#                 # "textUpdates": form.cleaned_data.get("text_updates", False),
#                 "password": form.cleaned_data["password"],
#             }
#             try:
#                 response = requests.post(
#                     "https://efile-test.suffolklitlab.org/jurisdictions/illinois/adminusers/users",
#                     json=data,
#                     timeout=10
#                 )
#                 if response.status_code == 201:
#                     messages.success(
#                         request,
#                         "Registration successful! Please log in with your new account."
#                     )
#                     return redirect("efile_login")
#                 else:
#                     # Try to get error message from API
#                     try:
#                         error_msg = response.json().get("error") or response.text
#                     except Exception:
#                         error_msg = response.text
#                     messages.error(request, f"Registration failed: {error_msg}")
#             except Exception as e:
#                 messages.error(request, f"Registration failed: {str(e)}")
#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = EFileRegistrationForm()
#     return render(request, "efile/register.html", {"form": form})

# # Dashboard view after successful login
# def dashboard(request):
#     """
#     Dashboard view after successful login
#     """
#     if not request.user.is_authenticated:
#         messages.info(request, 'Please log in to access your dashboard.')
#         return redirect('efile_login')

#     context = {
#         'user': request.user,
#         # If using UserProfile model:
#         # 'profile': getattr(request.user, 'userprofile', None)
#     }
#     return render(request, 'efile/dashboard.html', context)

# # Class-based view alternative (if you prefer)
# class EFileLoginRegisterView(TemplateView):
#     """
#     Class-based view for the eFile login page
#     """
#     template_name = 'efile/login.html'

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['login_form'] = EFileLoginForm()
#         return context

#     def post(self, request, *args, **kwargs):
#         login_form = EFileLoginForm(request.POST)
#         if login_form.is_valid():
#             email = login_form.cleaned_data['email']
#             password = login_form.cleaned_data['password']

#             try:
#                 user = User.objects.get(email=email)
#                 user = authenticate(request, username=user.username, password=password)
#                 if user is not None:
#                     login(request, user)
#                     messages.success(request, 'Successfully logged in!')
#                     next_page = request.GET.get('next', 'dashboard')
#                     return redirect(next_page)
#                 else:
#                     messages.error(request, 'Invalid email or password.')
#             except User.DoesNotExist:
#                 messages.error(request, 'No account found with this email address.')

#         context = self.get_context_data()
#         context['login_form'] = login_form
#         return render(request, self.template_name, context)

# # Password reset view (optional)
# def password_reset_request(request):
#     """
#     Handle password reset requests
#     """
#     if request.method == 'POST':
#         email = request.POST.get('email')
#         try:
#             user = User.objects.get(email=email)
#             # Here you would typically send a password reset email
#             # For now, we'll just show a success message
#             messages.success(
#                 request,
#                 'If an account with this email exists, you will receive password reset instructions.'
#             )
#             return redirect('efile_login')
#         except User.DoesNotExist:
#             # Don't reveal whether the email exists or not for security
#             messages.success(
#                 request,
#                 'If an account with this email exists, you will receive password reset instructions.'
#             )
#             return redirect('efile_login')

#     return render(request, 'efile/password_reset.html')


# Expert Form View
def expert_form(request):
    """
    Display the expert form for case details and parties
    """
    if request.method == 'POST':
        # Handle form submission
        # This would process the form data and save it
        messages.success(request, 'Case details saved successfully!')
        return redirect('dashboard')  # or next step
    
    # Get existing case data from session if available
    from .utils.case_data_utils import get_case_data
    case_data = get_case_data(request)
    
    print(f"Expert form view - case_data from session: {case_data}")
    
    context = {
        'case_data': case_data
    }
    
    return render(request, 'efile/expert_form.html', context)


# API Endpoints for Dynamic Form Configuration

@require_http_methods(["GET"])
def api_case_categories(request):
    """
    API endpoint to get all available case categories
    """
    try:
        categories = case_types_config.get_case_categories()
        return JsonResponse({
            'success': True,
            'data': categories
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_case_types(request):
    """
    API endpoint to get case types for a specific category
    """
    try:
        category_id = request.GET.get('parent')
        if not category_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing category parameter'
            }, status=400)
        
        case_types = case_types_config.get_case_types(category_id)
        return JsonResponse({
            'success': True,
            'data': case_types
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_filing_types(request):
    """
    API endpoint to get filing types for a specific case type
    """
    try:
        case_type_id = request.GET.get('parent')
        category_id = request.GET.get('category')
        
        if not case_type_id or not category_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            }, status=400)
        
        filing_types = case_types_config.get_filing_types(category_id, case_type_id)
        return JsonResponse({
            'success': True,
            'data': filing_types
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_document_types(request):
    """
    API endpoint to get document types for a specific filing type
    """
    try:
        filing_type_id = request.GET.get('parent')
        case_type_id = request.GET.get('case_type')
        category_id = request.GET.get('category')
        county = request.GET.get('county')
        
        if not filing_type_id or not case_type_id or not category_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            }, status=400)
        
        document_types = case_types_config.get_document_types(
            category_id, case_type_id, filing_type_id, county
        )
        return JsonResponse({
            'success': True,
            'data': document_types
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_counties(request):
    """
    API endpoint to get available counties
    """
    try:
        # This would typically come from a database or external API
        # For now, we'll return Illinois counties
        counties = [
            {'value': 'cook', 'text': 'Cook County'},
            {'value': 'dupage', 'text': 'DuPage County'},
            {'value': 'lake', 'text': 'Lake County'},
            {'value': 'kane', 'text': 'Kane County'},
            {'value': 'will', 'text': 'Will County'},
            {'value': 'mchenry', 'text': 'McHenry County'},
            {'value': 'winnebago', 'text': 'Winnebago County'},
            {'value': 'madison', 'text': 'Madison County'},
            {'value': 'st_clair', 'text': 'St. Clair County'},
            {'value': 'sangamon', 'text': 'Sangamon County'},
        ]
        
        # Filter by user preference if provided
        user_filter = request.GET.get('user_filter')
        if user_filter:
            # Move user's preferred county to the top
            preferred = [c for c in counties if c['value'] == user_filter]
            others = [c for c in counties if c['value'] != user_filter]
            counties = preferred + others
        
        return JsonResponse({
            'success': True,
            'data': counties
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_form_config(request):
    """
    API endpoint to get complete form configuration for a specific filing type
    """
    try:
        category_id = request.GET.get('category')
        case_type_id = request.GET.get('case_type')
        filing_type_id = request.GET.get('filing_type')
        
        if not all([category_id, case_type_id, filing_type_id]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            }, status=400)
        
        # Validate that the selection is valid
        validation = case_types_config.validate_selection(category_id, case_type_id, filing_type_id)
        if not all(validation.values()):
            return JsonResponse({
                'success': False,
                'error': 'Invalid selection combination'
            }, status=400)
        
        # Get complete form configuration
        config = case_types_config.get_form_config(category_id, case_type_id, filing_type_id)
        
        return JsonResponse({
            'success': True,
            'data': config
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_user_profile(request):
    """
    API endpoint to get user profile information
    """
    try:
        # Mock user profile data - replace with actual user data
        profile_data = {
            'username': 'john_doe',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@example.com',
            'preferred_county': 'cook',
            'location': {
                'county': 'Cook County',
                'state': 'Illinois'
            }
        }
        
        return JsonResponse({
            'success': True,
            'data': profile_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# # Logout view (optional custom implementation)
def efile_logout(request):
    """
    Custom logout view
    """
    from django.contrib.auth import logout

    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect("efile_login")
