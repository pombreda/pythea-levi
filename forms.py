import logging
import datetime

from google.appengine.ext.webapp import template

from google.appengine.ext.db import djangoforms as df
from django import forms
import re
import models

class ClientForm(df.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, required=False, label='Wachtwoord')
    password2 = forms.CharField(widget=forms.PasswordInput, required=False, label='Wachtwoord controle')
    ssn = forms.CharField(label="Burger Service Nummer", required=False)
    birthdate = forms.DateField(localize=True, widget=forms.TextInput(attrs={'class':'date'}))

    phone_p = re.compile(r'(^\+[0-9]{2}|^\+[0-9]{2}\(0\)|^\(\+[0-9]{2}\)\(0\)|^00[0-9]{2}|^0)([0-9]{9}$|[0-9\-\s]{10}$)')
    class Meta:
        model = models.Client
        #exclude = ['display_name', '_class', 'password', 'username', 'is_active', 'is_staff', 'is_superuser']
        fields = ['first_name', 'last_name', 'username', 'email', 'address', 'zipcode', 'city', 'phone', 'mobile', 'birthdate', 'ssn']

    def clean(self):
        data = self.cleaned_data
        password1 = data.get('password1')
        password2 = data.get('password2')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        username = data.get('username')
        if not self.instance:
            data['key_name'] = username
        #username = "%s.%s" % (first_name.lower(), last_name.lower())
        #data['username'] = username
        phone = data.get('phone')
        mobile = data.get('mobile')
        email = data.get('email')

        # try to find the given username
        try:
            user = models.Client.get_by_key_name(username)
        except Exception, e:
            user = False

        # try to find the given email
        try:
            user_by_email = models.Client.gql("WHERE email = :1",email).get()
        except Exception, e:
            user_by_email = False

        if user and not self.instance:
            self._errors['username'] = self.error_class(['Er bestaat al een gebruiker met deze naam'])
        elif self.instance and self.instance.username != username:
            self._error['username'] = self.error_class(['Kan een bestaande username niet veranderen.'])
        elif (not self.instance and user_by_email) or (self.instance and self.instance.key() != user_by_email.key()):
            self._errors['email'] = self.error_class(['Dit e-mail adres is reeds in gebruik'])
        elif phone:
            m = self.phone_p.match(phone)
            if m:
                data['phone'] = '+31' + m.group(2)
                phone_exists = models.Client.gql("WHERE phone = :1",data['phone']).get()
            if m and m.group(2).startswith('6') and not mobile:
                data['mobile'] = '+31' + m.group(2)
            if not m:
                self._errors['phone'] = self.error_class(['Geen geldig telefoonnummer'])
            elif (not self.instance and phone_exists) or (self.instance and self.instance.key() != phone_exists.key()):
                self._errors['phone'] = self.error_class(['Dit nummer is reeds in gebruik'])
        if mobile:
            m = self.phone_p.match(mobile)
            if not m or not m.group(2).startswith('6'):
                self._errors['mobile'] = self.error_class(['Geen geldig mobiel nummer'])
            elif m:
                data['mobile'] = '+31' + m.group(2)
                mobile_exists = models.Client.gql("WHERE mobile = :1",data['mobile']).get()
                if (not self.instance and mobile_exists) or (self.instance and self.instance.key() != mobile_exists.key()):
                    self._errors['mobile'] = self.error_class(['Dit nummer is reeds in gebruik'])
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
    password1 = forms.CharField(widget=forms.PasswordInput, required=False, label='Wachtwoord')
    password2 = forms.CharField(widget=forms.PasswordInput, required=False, label='Wachtwoord controle')

    class Meta:
        model = models.SocialWorker
        fields = ['first_name', 'last_name', 'email', 'address', 'phone', 'mobile', 'photo']

    def clean(self):
        data = self.cleaned_data
        if not self.instance:
            data['key_name'] = data['email']
        else:
            if self.instance.email != data['email']:
                self._errors['email'] = self.error_class(['Kan het email adres niet veranderen'])
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
        exclude = ['_class', 'icon', 'tags', 'categories', 'approved', 'private_for']

class DebtForm(df.ModelForm):
    response_date = forms.DateField(localize=True, widget=forms.TextInput(attrs={'class':'date'}))
    amount = forms.DecimalField(localize=True, required=False, widget=forms.TextInput(attrs={'class':'currency'}))
    payment_amount = forms.DecimalField(localize=True, required=False, widget=forms.TextInput(attrs={'class':'currency'}))
    class Meta:
        model = models.Debt
        fields = ['response_date', 'creditor_dossier_number', 'collector_dossier_number', 'amount', 'payment_amount']

class LoginForm(forms.Form):
    userid = forms.CharField(label='Gebruikersnaam')
    password = forms.CharField(widget=forms.PasswordInput, label='Wachtwoord')

