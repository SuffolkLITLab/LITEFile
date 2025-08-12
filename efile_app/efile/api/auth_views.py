"""
API views for authentication and user management
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
import requests
import json
from .base import APIResponseMixin, validate_request


class AuthAPIViews(APIResponseMixin):
    """API views for authentication"""
    
    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_login(request):
        """Handle user login"""
        try:
            data = json.loads(request.body)
            
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                return AuthAPIViews.error_response("Username and password required")
            
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                return AuthAPIViews.success_response({
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email
                }, "Login successful")
            else:
                return AuthAPIViews.error_response("Invalid credentials", 401)
                
        except json.JSONDecodeError:
            return AuthAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_logout(request):
        """Handle user logout"""
        try:
            logout(request)
            return AuthAPIViews.success_response({}, "Logout successful")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["GET"])
    def user_profile(request):
        """Get current user profile"""
        try:
            if not request.user.is_authenticated:
                return AuthAPIViews.error_response("Not authenticated", 401)
            
            user_data = {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'date_joined': request.user.date_joined.isoformat(),
                'last_login': request.user.last_login.isoformat() if request.user.last_login else None
            }
            
            return AuthAPIViews.success_response(user_data)
            
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def external_auth(request):
        """Handle authentication with external Suffolk eFile API"""
        try:
            data = json.loads(request.body)
            
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                return AuthAPIViews.error_response("Username and password required")
            
            # Authenticate with Suffolk eFile API
            auth_response = requests.post(
                'https://suffolkefile.com/api/auth/login',
                json={
                    'username': username,
                    'password': password
                }
            )
            
            if auth_response.status_code == 200:
                auth_data = auth_response.json()
                
                # Store auth tokens in session
                request.session['auth_tokens'] = {
                    'access_token': auth_data.get('access_token'),
                    'refresh_token': auth_data.get('refresh_token'),
                    'expires_in': auth_data.get('expires_in')
                }
                
                return AuthAPIViews.success_response({
                    'authenticated': True,
                    'user': auth_data.get('user', {})
                }, "External authentication successful")
            else:
                return AuthAPIViews.error_response("External authentication failed", 401)
                
        except json.JSONDecodeError:
            return AuthAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
user_login = AuthAPIViews.user_login
user_logout = AuthAPIViews.user_logout
user_profile = AuthAPIViews.user_profile
external_auth = AuthAPIViews.external_auth
