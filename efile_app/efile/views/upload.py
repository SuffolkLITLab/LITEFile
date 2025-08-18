from django.shortcuts import redirect, render
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import requests
import json
import logging
from ..utils.case_data_utils import get_case_data, get_petitioner_info, get_name_sought_info, get_case_classification
from ..utils.s3_upload import s3_handler

logger = logging.getLogger(__name__)


def efile_upload(request):
    """Upload view for document submission and filing creation."""
    
    # Get case data from session
    case_data = get_case_data(request)
    
    # If no case data exists, redirect back to expert form
    if not case_data:
        messages.error(request, 'Please complete the case details first.')
        return redirect('expert_form')
    
    # Get organized case information
    petitioner_info = get_petitioner_info(request)
    name_sought_info = get_name_sought_info(request)
    case_classification = get_case_classification(request)
    
    # Use friendly names if available, otherwise fallback to raw values
    friendly_case_type = case_data.get('case_type_name', case_classification['case_type'])
    friendly_filing_type = case_data.get('filing_type_name', case_classification['filing_type'])
    friendly_court = case_data.get('court_name', case_classification['court'])
    
    context = {
        'case_data': case_data,
        'petitioner_info': petitioner_info,
        'name_sought_info': name_sought_info,
        'case_classification': case_classification,
        'case_type': friendly_case_type,
        'filing_type': friendly_filing_type,
        'court': friendly_court,
        'case_type_raw': case_classification['case_type'],
        'filing_type_raw': case_classification['filing_type'],
        'court_raw': case_classification['court'],
    }

    return render(request, 'efile/upload.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def create_filing(request):
    """Create a filing with Suffolk LIT Lab API using collected case data."""
    
    try:
        # Get case data from session
        case_data = get_case_data(request)
        
        if not case_data:
            return JsonResponse({
                'success': False,
                'error': 'No case data found. Please complete the expert form first.'
            }, status=400)
        
        # Get auth tokens
        auth_tokens = request.session.get('auth_tokens')
        if not auth_tokens or 'token' not in auth_tokens:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required. Please log in first.'
            }, status=401)
        
        # Transform case data to Suffolk API payload format
        filing_payload = transform_case_data_to_filing_payload(case_data)
        
        # Make POST request to Suffolk LIT Lab filing API
        api_url = "https://efile-test.suffolklitlab.org/filings/"
        
        headers = {
            'Authorization': f"Bearer {auth_tokens['token']}",
            'Content-Type': 'application/json'
        }
        
        response = requests.post(api_url, headers=headers, json=filing_payload, timeout=30)
        
        if response.status_code == 201:
            # Filing created successfully
            filing_data = response.json()
            
            # Save filing ID to session for future reference
            request.session['current_filing_id'] = filing_data.get('id')
            request.session.modified = True
            
            return JsonResponse({
                'success': True,
                'filing_id': filing_data.get('id'),
                'message': 'Filing created successfully',
                'data': filing_data
            })
        else:
            # API error
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = error_json.get('detail', error_json)
            except:
                pass
                
            return JsonResponse({
                'success': False,
                'error': f'Filing creation failed: {error_detail}',
                'status_code': response.status_code
            }, status=response.status_code)
            
    except requests.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Network error: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


def transform_case_data_to_filing_payload(case_data):
    """
    Transform collected case data into Suffolk LIT Lab API filing payload format.
    """
    
    # Base filing payload structure
    payload = {
        'jurisdiction': 'illinois',
        'court': case_data.get('court'),
        'category': case_data.get('case_category'),
        'case_type': case_data.get('case_type'),
        'filing_type': case_data.get('filing_type'),
        'document_type': case_data.get('document_type'),
        'parties': [],
        'optional_services': case_data.get('optional_services', [])
    }
    
    # Add petitioner party if this is a name change case
    if 'name change' in case_data.get('case_type', '').lower():
        # Add petitioner
        if case_data.get('petitioner_first_name') or case_data.get('petitioner_last_name'):
            petitioner = {
                'party_type': 'petitioner',
                'name': {
                    'first': case_data.get('petitioner_first_name', ''),
                    'last': case_data.get('petitioner_last_name', ''),
                    'full': f"{case_data.get('petitioner_first_name', '')} {case_data.get('petitioner_last_name', '')}".strip()
                },
                'address': case_data.get('petitioner_address', ''),
                'role': 'Petitioner'
            }
            payload['parties'].append(petitioner)
        
        # Add name sought information as additional case details
        if case_data.get('new_first_name') or case_data.get('new_last_name'):
            payload['name_change_details'] = {
                'new_name': {
                    'first': case_data.get('new_first_name', ''),
                    'last': case_data.get('new_last_name', ''),
                    'full': f"{case_data.get('new_first_name', '')} {case_data.get('new_last_name', '')}".strip()
                }
            }
    
    # Add case metadata
    payload['metadata'] = {
        'created_via': 'illinois_efile_system',
        'case_classification': {
            'court': case_data.get('court'),
            'category': case_data.get('case_category'),
            'case_type': case_data.get('case_type'),
            'filing_type': case_data.get('filing_type'),
            'document_type': case_data.get('document_type')
        }
    }
    
    return payload


@csrf_exempt  
@require_http_methods(["POST"])
def upload_documents(request):
    """Handle document uploads using S3, then submit to Suffolk API."""
    
    try:
        # Get current filing ID from session
        filing_id = request.session.get('current_filing_id')
        
        if not filing_id:
            return JsonResponse({
                'success': False,
                'error': 'No active filing found. Please create a filing first.'
            }, status=400)
        
        # Get auth tokens
        auth_tokens = request.session.get('auth_tokens')
        if not auth_tokens or 'token' not in auth_tokens:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required.'
            }, status=401)
        
        # Handle file uploads
        uploaded_files = request.FILES.getlist('documents')
        file_type = request.POST.get('file_type', 'document')
        
        if not uploaded_files:
            return JsonResponse({
                'success': False,
                'error': 'No documents provided.'
            }, status=400)
        
        s3_upload_results = []
        
        # First upload all files to S3
        for uploaded_file in uploaded_files:
            # Validate file
            validation_result = s3_handler.validate_file(
                uploaded_file, 
                max_size_mb=10, 
                allowed_types=['.pdf']  # Only PDFs for efile
            )
            
            if not validation_result['valid']:
                return JsonResponse({
                    'success': False,
                    'error': f'File validation failed for {uploaded_file.name}: {validation_result["error"]}'
                }, status=400)
            
            # Prepare metadata
            metadata = {
                'file-type': file_type,
                'filing-id': str(filing_id),
                'original-size': str(uploaded_file.size),
                'original-name': uploaded_file.name
            }
            
            # Upload to S3
            upload_result = s3_handler.upload_file(
                uploaded_file, 
                file_type=file_type,
                metadata=metadata
            )
            
            if not upload_result['success']:
                return JsonResponse({
                    'success': False,
                    'error': f'S3 upload failed for {uploaded_file.name}: {upload_result["error"]}'
                }, status=500)
                print(upload_result)  # Debugging line, can be removed later
            s3_upload_results.append({
                'original_name': uploaded_file.name,
                'url': upload_result['url'],
                'public_url': s3_handler.get_public_url(upload_result['key']),
                'key': upload_result['key'],
                'size': upload_result['size']
            })
        print("DEBUG: S3 upload results:", s3_upload_results)

        # Now submit the S3 URLs to Suffolk API
        submitted_documents = []
        
        for s3_result in s3_upload_results:
            # Submit document URL to Suffolk API instead of uploading file
            document_payload = {
                'filing_id': filing_id,
                'document_url': s3_result['public_url'],  # Use public S3 URL
                'document_name': s3_result['original_name'],
                'document_size': s3_result['size']
            }
            
            api_url = f"https://efile-test.suffolklitlab.org/filings/{filing_id}/documents/"
            
            headers = {
                'Authorization': f"Bearer {auth_tokens['token']}",
                'Content-Type': 'application/json'
            }
            
            response = requests.post(api_url, headers=headers, json=document_payload, timeout=60)
            
            if response.status_code == 201:
                document_data = response.json()
                document_data['s3_url'] = s3_result['public_url']
                document_data['s3_key'] = s3_result['key']
                submitted_documents.append(document_data)
            else:
                # If submission fails, we should clean up the S3 file
                logger.warning(f"Failed to submit document to Suffolk API, cleaning up S3 file: {s3_result['key']}")
                s3_handler.delete_file(s3_result['key'])
                
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to submit {s3_result["original_name"]} to Suffolk API: {response.text}'
                }, status=response.status_code)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully uploaded {len(submitted_documents)} document(s)',
            'documents': submitted_documents,
            's3_uploads': s3_upload_results
        })
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Upload error: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def test_s3_connection(request):
    """Test S3 connection and bucket access."""
    try:
        # Reinitialize the global handler to pick up the corrected credentials
        global s3_handler
        from ..utils.s3_upload import S3UploadHandler
        s3_handler = S3UploadHandler()
        
        # Test S3 connection
        if s3_handler._ensure_initialized():
            response = s3_handler.s3_client.list_objects_v2(
                Bucket=s3_handler.bucket_name,
                MaxKeys=1
            )
            
            return JsonResponse({
                'success': True,
                'message': 'S3 connection successful',
                'bucket': s3_handler.bucket_name,
                'region': s3_handler.region_name,
                'objects_exist': 'Contents' in response
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'S3 client not initialized - check AWS credentials'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'S3 connection failed: {str(e)}'
        })