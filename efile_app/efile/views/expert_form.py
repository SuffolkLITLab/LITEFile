from django.contrib import messages
from django.shortcuts import redirect, render

from ..forms import EFileExpertForm


def efile_expert_form(request):
    """Expert form view for creating filings with cascading dropdowns."""
    # Get auth tokens from session if available
    auth_tokens = request.session.get('auth_tokens', None)
    print(f"Auth Tokens: {auth_tokens}")
    
    if request.method == 'POST':
        form = EFileExpertForm(request.POST)
        if form.is_valid():
            # Process the form data
            messages.success(request, 'Expert form submitted successfully.')
            return redirect('options')
    else:
        form = EFileExpertForm()
    
    return render(request, 'efile/expert_form.html', {'form': form})