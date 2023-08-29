from django.shortcuts import render, redirect
from django.db import IntegrityError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, UserUpdateForm


def register(request):
    form = UserRegisterForm()
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        try:
            form.save()
            # Handle successful registration, maybe redirect to a success page or login page
        except IntegrityError:  # Ensure you've imported IntegrityError from django.db
            messages.error(request, 'A user with that identity already exists.')
            return redirect('login')

        username = form.cleaned_data.get('username')
        messages.success(request, f'Account created for {username}. Please login.')
        return redirect('login')
    else:
        context = {
                    'form': form,
                   }
    return render(request, 'users/register.html', context)


@login_required()
def profile(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        if u_form.is_valid():
            u_form.save()
            messages.success(request, f'Your account has been updated.')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)

    context = {
        'u_form': u_form,

    }
    return render(request, 'users/profile.html', context)
