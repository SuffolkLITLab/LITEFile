from django.shortcuts import redirect, render


def efile_options(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "file_new_case":
            return redirect("file_new_case_url")  # Replace with your actual URL name
        elif action == "respond_to_case":
            return redirect("respond_to_case_url")
        elif action == "add_to_case":
            return redirect("add_to_case_url")
        else:
            return redirect("options")
    return render(request, "efile/options.html")
