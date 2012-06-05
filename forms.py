import logging
import datetime

from google.appengine.ext.webapp import template

from google.appengine.ext.db import djangoforms as df
from django import forms
import re
import models

class ClientForm(df.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(widget=forms.PasswordInput, required=False)
  
    phone_p = re.compile(r'(^\+[0-9]{2}|^\+[0-9]{2}\(0\)|^\(\+[0-9]{2}\)\(0\)|^00[0-9]{2}|^0)([0-9]{9}$|[0-9\-\s]{10}$)')
    class Meta:
        model = models.Client
        #exclude = ['display_name', '_class', 'password', 'username', 'is_active', 'is_staff', 'is_superuser']
        fields = ['first_name', 'last_name', 'email', 'address', 'zipcode', 'city', 'phone', 'mobile']

    def clean(self):
        if self.instance:
           logging.info("We have an instance")

        data = self.cleaned_data
        password1 = data.get('password1')
        password2 = data.get('password2')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        username = "%s.%s" % (first_name.lower(), last_name.lower())
        data['username'] = username
        # FIXME: we should check if the username already exists in the database
        data['key_name'] = username
        phone = data.get('phone')
        mobile = data.get('mobile')
        if phone:
            m = self.phone_p.match(phone)
            if m:
                data['phone'] = '+31' + m.group(2)
            if m and m.group(2).startswith('6') and not mobile:
                data['mobile'] = '+31' + m.group(2)
            if not m:
                self._errors['phone'] = self.error_class(['Geen geldig telefoonnummer'])
        if mobile:
            m = self.phone_p.match(mobile)
            if not m or not m.group(2).startswith('6'):
                self._errors['mobile'] = self.error_class(['Geen geldig mobiel nummer'])
            elif m:
                data['mobile'] = '+31' + m.group(2)
        if not self.instance and not password1:
            self._errors['password1'] = self.error_class(['Wachtwoord is verplicht'])
        if password1 != password2:
            raise forms.ValidationError('De wachtwoorden zijn niet hetzelfde')
        return data

class SocialWorkForm(df.ModelForm):
    class Meta:
        model = models.SocialWork
        exclude = ['display', '_class', 'icon', 'zipcodes']

class SocialWorkerForm(df.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = models.SocialWorker
        fields = ['first_name', 'last_name', 'email', 'address', 'phone', 'mobile', 'photo']

    def clean(self):
        data = self.cleaned_data
        data['key_name'] = data['email']
        password1 = data.get('password1')
        password2 = data.get('password2')
        if password1 != password2:
            raise forms.ValidationError('De wachtwoorden zijn niet hetzelfde')
        return data

class CategoryForm(df.ModelForm):
    class Meta:
        model = models.Category

class CreditorForm(df.ModelForm):
    class Meta:
        model = models.Creditor
        exclude = ['display_name', '_class', 'icon', 'tags']

class DebtForm(df.ModelForm):
    #creditor_or_collector = forms.CharField()
    class Meta:
        model = models.Debt
        fields = ['original_date', 'creditor_dossier_number', 'collector_dossier_number', 'amount', 'payment_amount']

