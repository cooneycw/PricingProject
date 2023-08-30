from django.shortcuts import render, redirect
from django.db import IntegrityError
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, UserUpdateForm


def register(request):
    form = UserRegisterForm()
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')
            # Check if a user with the given username or email already exists
            if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
                messages.warning(request, 'A user with that username or email already exists.')
            else:
                form.save()
                messages.success(request, f'Account created for {username}. Please login.')
                return redirect('login')
    context = {'form': form}

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
