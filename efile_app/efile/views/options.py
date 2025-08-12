from django.shortcuts import render, redirect

def efile_options(request):
    return render(request, 'efile/options.html')
