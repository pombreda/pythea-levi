from __future__ import with_statement
from google.appengine.dist import use_library
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
use_library('django', '1.3')
import logging
import cgi
import datetime
import urllib
import csv
import pickle
import crypt
from StringIO import StringIO
import urlparse
import re


#from google.appengine.ext.db import polymodel
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api.urlfetch import fetch
from google.appengine.api import mail
from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api import taskqueue

import wsgiref.handlers
import webob
from collections import defaultdict

from gaesessions import get_current_session

import simplejson as json

import models
import forms
import docs
import yaml

import inspect
import django

import locale
import decimal

class BaseHandler(webapp.RequestHandler):
    def get_user(self):
        try:
            return self.session['user']
        except KeyError:
            return None

    def get_admin(self):
        from google.appengine.api import users
        return users.get_current_user()

    def get_session(self):
        try:
            return get_current_session()
        except Exception:
            return None

    def dump(self):
        self.response.out.write('<table>')
        for key in self.request.arguments():
            self.response.out.write('<tr><td>%s</td><td>%s</td></tr>' % (key, self.request.get_all(key)))
        self.response.out.write('</table>')

    user = property(get_user)
    admin = property(get_admin)
    session = property(get_session)

    def redirect(self, uri, permanent=False):
        if 'x-text/html-fragment' in self.request.headers['Accept']: #or 'JSON' in self.session:
            status = 200
        elif permanent:
            status = 301
        else:
            status = 302
        self.response.set_status(status)
        self.response.headers['Location'] = str(uri)
        self.response.headers['Content-Type'] = 'text/plain'

    def tabs(self):
        if self.user:
            return self.user.tabs()
        else:
            t = (("/info/clienten.html", "Info"),
                    ("/info/werkwijze.html", "Werkwijze"),
                    ("/client/register", "Aanmelden"))
            logging.error(t)
            return t


    def render(self, vars, templ=None):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        if not template or 'application/json' in self.request.headers['Accept']: #or 'JSON' in self.session:
            self.response.headers['Content-Type'] = 'application/json'
        else:
            screen_id = '%s@%s' % (templ, self.request.path)
            screen = models.Screen.get_or_insert(screen_id)
            if self.admin and templ not in ['login.html', 'main.html']:
                path = os.path.join(os.path.dirname(__file__), 'templates', 'admin_plus.html')
                admin_vars = {'template': templ, 'self': self}
                self.response.out.write(template.render(path, admin_vars))

            if templ != 'main.html':
                path = os.path.join(os.path.dirname(__file__), 'templates', 'session_info.html')
                self.response.out.write(template.render(path, {'self': self}))

            path = os.path.join(os.path.dirname(__file__), 'templates', templ)
            vars['self'] = self
            vars['FILE'] = templ
            self.response.out.write(template.render(path, vars))

class Main(BaseHandler):
    def get(self):
        """Show the default screen. This is now the login screen"""
        user = self.user
        self.session['JSON'] = False
        message = self.request.get("message")
        vars = {
                 'message': message,
                 'user': user }
        self.render(vars, 'main.html')


class Screens(BaseHandler):
    def get(self):
        """A utility screen to display all screens inside the application"""
        doc = docs.Document(application, self)
        self.render( {'docs': doc.docs, 'tree': dict(doc.tree)}, 'screens.html' )


class ClientEdit(BaseHandler):
    def get(self):
        """Show the form to add a new client"""
        if self.user:
            form = forms.ClientForm(instance=self.user)
        else:
            form = forms.ClientForm()
        message = self.request.get("message")
        form.title = 'Registreer'
        vars = { 'forms': [form] , 'title': 'Registreer', 'message': message}
        self.render(vars, 'form.html')

    def post(self):
        """Enter the new client"""
        # Read form variables and put the new user in the database
        mode = "create"
        if self.user:
            form = forms.ClientForm(self.request.POST, instance=self.user)
            mode = "update"
        else:
            form = forms.ClientForm(self.request.POST)
        if form.is_valid():
            logging.info("user okay")  #FIXME: need to make sure users are not overwritten if they have an existing name
            new_user = form.save(commit=False)
            if form.cleaned_data['password1']:
                new_user.set_password(form.cleaned_data['password1'])
            new_user.put()
            session = get_current_session()
            if session.is_active():
                session.terminate()
            session['user'] = new_user
            if mode == "create":
                self.redirect('/client/register/contact')
            else:
                message = "Success"
                self.redirect("%s?message=%s" % (self.request.path, message))
        else:
            message = "Fout in formulier"
            vars = { 'forms': [form], 'title': 'Registreer', 'message': message}
            self.render(vars, 'form.html')


class ClientContact(BaseHandler):
    def get(self):
        """Show a list of possible contact persons"""
        user = self.user
        zipcode = user.zipcode
        orgs = [ i for i in models.SocialWork.all() if i.accepts(zipcode)]

        vars = { 'user': user,
                 'organisations': orgs,
                 'title': 'Met wie heeft u gesproken?' }
        self.render(vars, 'addcontact.html')

    def post(self):
        """Add the selected contact person to the database"""
        selected = self.request.get("selected")
        user = self.user
        contact = models.SocialWorker.get(selected)
        user.contact = contact
        user.put()
        self.redirect('/client/creditors')


class ClientSelectCreditors(BaseHandler):
    def get(self, category=None):
        """Show a list of available creditors
        """
        if not category:
            category = 'Banken'
        user = self.user
        #FIXME: we should cache this
        creditors = models.Creditor.all()
        categories = models.Category.all()

        creditors.filter('categories =', category)
        creditors_2 = []
        for creditor in creditors:
            if creditor.private_for == None or creditor.private_for.key() == user.key():
                creditor.selected = user.hasCreditor(creditor)
                creditors_2.append(creditor)

        vars = { 'categories': categories,
                 'selected': category,
                 'creditors': creditors_2,
                 'user': user }
        self.render(vars, 'crediteuren.html')

    def post(self, category=None):
        action = self.request.get('klaar')
        logging.error("action  %s" % (action))
        if action == 'klaar':
            self.redirect('/client/creditors/validate')
            return
        user = self.user
        creditor = int(self.request.get('creditor'))
        checked = self.request.get('checked') == 'true'
        cred = models.Creditor.get_by_id(creditor)
        if checked:
            user.addCreditor(cred)
        else:
            user.removeCreditor(cred)
        self.redirect(self.request.url)


class ClientAddCreditor(BaseHandler):
    def get(self, category):
        """Add a new creditor that is specific to this client"""
        form = forms.CreditorForm(initial={'category':category})
        vars = { 'forms': [form] }
        self.render(vars, 'form.html')

    def post(self, category):
        """Add the creditor to the database"""
        form = forms.CreditorForm(self.request.POST)
        if form.is_valid():
            creditor = form.save(commit=False)
            #creditor.expand()
            creditor.categories = [category]
            creditor.private_for = self.user
            creditor.approved = False
            creditor.put()
            self.user.addCreditor(creditor)
            self.redirect('/client/creditors/category/%s' % category)
        else:
            vars = { 'forms': [form] }
            self.render(vars, 'form.html')


class ClientValidate(BaseHandler):
    def get(self):
        """Validate a new client"""
        user = self.user
        vars = {
                 'user': user }
        self.render(vars, 'clientcontactcreditors.html')

    def post(self):
        action = self.request.get('action')
        if action != 'go back':
            client = self.user
            client.complete()
            mail.send_mail(sender="No reply <hans.then@gmail.com>",
                           to="<h.then@pythea.nl>",
                           subject="Dossier Entered",
                           body="Dossier is toegevoegd voor %s %s" % (client.first_name, client.last_name))
            letters = []
            for creditor in client.creditors:
                if not creditor.last_email_date:
                    method = creditor.creditor.contact_method()
                    letter = creditor.generate_letter()
                    if method in ['EMAIL', 'FAX']:
                        logging.info("Sending letter to %s by %s" % (creditor.creditor.display_name, method))
                        creditor.send_message("Verzoek schuldbewijs", letter)
                        creditor.status = method
                    elif method == 'POST':
                        logging.info("Sending letter to %s by %s" % (creditor.creditor.display_name, method))
                        creditor.status = method
                        # FIXME: generate a letter
                        letters.append(letter)
            """
            for key in self.request.arguments():
                letters = []
                if key.startswith("creditor-"):
                    id = int(key.split("-")[1])
                    creditor = models.CreditorLink.get_by_id(id)
                    method = creditor.creditor.contact_method()
                    letter = creditor.generate_letter()
                    if method in ['EMAIL', 'FAX']:
                        logging.info("Sending letter to %s by %s" % creditor.creditor.display_name, method)
                        creditor.send_message("Verzoek schuldbewijs", letter)
                        creditor.status = method
                    elif method == 'POST':
                        logging.info("Sending letter to %s by %s" % creditor.creditor.display_name, method)
                        creditor.status = method
                        # FIXME: generate a letter
                        letters.append(letter)

                    estimated_amount = self.request.get(key)
                    try:
                        estimated_amount = decimal.Decimal(str(float(estimated_amount)))
                    except ValueError:
                        try:
                            estimated_amount = estimated_amount.replace(".", "").replace(",", ".")
                            logging.error(estimated_amount)
                            estimated_amount = decimal.Decimal(estimated_amount)
                        except decimal.InvalidOperation, e:
                            estimated_amount = decimal.Decimal('0.00')
                    except decimal.InvalidOperation, e:
                        estimated_amount = decimal.Decimal('0.00')
                    creditor = models.CreditorLink.get_by_id(id)
                    if creditor.estimated_amount != estimated_amount:
                        creditor.estimated_amount = estimated_amount
                        creditor.put()
            """

            self.redirect('/client/debts')
        else:
            self.redirect('/client/creditors')


class ClientSubmitted(BaseHandler):
    def get(self):
        user = self.get_user()
        message = 'De gegevens worden naar uw maatschappelijk werker gestuurd voor controle.'
        vars = { 'user': user,
                 'message': message }
        self.render(vars, 'message.html')

class ClientRegisterPreviewLetter(BaseHandler):
    def get(self, creditor):
        """Voorbeeld brief aan een schuldeiser"""
        key = creditor
        creditor = models.CreditorLink.get_by_id(int(creditor))
        user = creditor.user
        creditor = creditor.creditor
        path = os.path.join(os.path.dirname(__file__), 'brieven', 'schuldeiser-1.html')
        vars = {}
        vars['client'] = user
        vars['key'] = key
        vars['creditor'] = creditor
        vars['today'] = datetime.date.today().strftime("%d-%m-%Y")
        vars['preview'] = True
        self.response.out.write(template.render(path, vars))

class ClientRegisterPrintLetter(BaseHandler):
    def get(self, creditor):
        """Verstuur een brief aan een schuldeiser"""
        key = creditor
        creditor = models.CreditorLink.get_by_id(int(creditor))
        creditor.cached_state = None
        creditor.last_email_date = datetime.date.today()
        creditor.put()
        user = creditor.user
        creditor = creditor.creditor
        path = os.path.join(os.path.dirname(__file__), 'brieven', 'schuldeiser-1.html')
        vars = {}
        vars['client'] = user
        vars['creditor'] = creditor
        vars['today'] = datetime.date.today().strftime("%d-%m-%Y")
        vars['preview'] = False
        html = template.render(path, vars)
        from google.appengine.api import conversion
        asset = conversion.Asset("text/html", html, "schuldeiser.html")
        conversion_obj = conversion.Conversion(asset, "application/pdf")
        result = conversion.convert(conversion_obj)
        if not result.assets:
            self.response.out.write("error genering pdf")
        else:
            self.response.headers['Content-Type'] = 'application/pdf'
            for asset in result.assets:
                self.response.out.write(asset.data)

class ClientDebts(BaseHandler):
    def get(self, creditor=None):
        user = self.get_user()
        base_url = '/client/debts'
        if not creditor:
            creditor = user.creditors.get()
            # FIXME: what if there is no creditor?
            self.redirect('%s/creditor/%s' % (user.key(), creditor.key().id()))
        else:
            creditor = models.CreditorLink.get_by_id(int(creditor))
        annotations = creditor.annotations.order('-entry_date').run(limit=3)
        vars = { 'client': user,
                 'creditor': creditor,
                 'annotations': annotations,
                 'base_url': base_url }
        self.render(vars, 'clientdebts.html')

    def post(self):
        user = self.get_user()
        message = 'U bent klaar'
        vars = { 'user': user,
                 'message': message }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'message.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'message.html')


class ClientDebtsView(BaseHandler):
    def get(self, creditor):
        client = self.user
        creditor = models.CreditorLink.get_by_id(int(creditor))
        form = forms.DebtForm()
        ## GETGET
        selected = self.request.get('selected')
        if selected:
            selected = models.Creditor.get_by_id(int(selected))

        vars = { 'client': client,
                 'creditor': creditor,
                 'selected': selected,
                 'form': form }
        if creditor.creditor.is_collector:
            self.render(vars, 'clientdebtsview_collector.html')
        else:
            self.render(vars, 'clientdebtsview.html')

    def post(self, creditor):
        user = self.get_user()
        form = forms.DebtForm(self.request.POST)
        creditor = models.CreditorLink.get_by_id(int(creditor))
        selected = self.request.get('selected')
        if selected:
            selected = models.Creditor.get_by_id(int(selected))
        else:
            selected = None
        if form.is_valid():
            new_debt = form.save(commit=False)
            new_debt.creditor = creditor
            if creditor.creditor.is_collector:
                new_debt.collected_for = selected
            else:
                new_debt.collector = selected
            new_debt.put()
            url = urlparse.urlsplit(self.request.url)
	    self.redirect(url.path)
        else:
            vars = { 'user': user,
                     'client': user,
                     'creditor': creditor,
                     'selected': selected,
                     'form': form }
            if creditor.creditor.is_collector:
                self.render(vars, 'clientdebtsview_collector.html')
            else:
                self.render(vars, 'clientdebtsview.html')

            #self.response.out.write(template.render(path, vars))


class ClientDebtsSelectCreditor(BaseHandler):
    """This is used to select a 'deurwaarder' for a debt (or a creditor in case of a 'deurwaarder'"""
    def get(self, selected=None):
        user = self.get_user()
        come_from = self.request.get('come_from') # Dit is het id van de CreditorLink
        creditor = models.CreditorLink.get_by_id(int(come_from))
        client = creditor.user

        is_collector = self.request.get('is_collector') == 'True'
        if not selected:
            creditors = models.Creditor.all()
            #creditors.filter('display_name =', 'Woonbron')
            creditors = creditors.filter('is_collector !=', is_collector)
            if user.class_name() == 'Client':
                base_url = "/client/debts"
            else:
                base_url = "/employee/cases/view/%s" % client.key()

            vars = { 'user': user,
                     'client': client,
                     'base_url': base_url,
                     'come_from': come_from,
                     'is_collector': is_collector,
                     'creditors': creditors }
            self.render(vars, 'clientdebtsselectcreditor.html')
        else:
            self.redirect("%s/view/%s?selected=%s" % (base_url, urllib.unquote(come_from), selected))

    def post(self, *args, **kwargs):
        self.get(*args, **kwargs)

class ClientDebtsCreditorActions(BaseHandler):
    """Show details for a CreditorLink"""
    def get(self, selected):
        user = self.user
        creditor = models.CreditorLink.get_by_id(int(selected))
        #annotations = creditor.annotations.order('-entry_date')
        annotations = creditor.annotations
        vars = { 'client': user,
                 'creditor': creditor,
                 'annotations': annotations,
                 }

        self.render(vars, 'clientdebtscreditoractions.html')

    def post(self, selected):
        user = self.get_user()
        creditor = models.CreditorLink.get_by_id(int(selected))
        come_from = self.request.get('come_from')
        text = self.request.get('text')
        if text:
            annotation = models.Annotation(subject=creditor, author=user, text=text)
            annotation.put()
        logging.info(come_from)
        self.redirect(come_from)

class ClientDebtsPrintDossier(BaseHandler):
    """Show all debts for a creditor"""
    def get(self, client=None):
        if not client:
            client = self.user
        else:
            client = models.Client.get(client)
        vars = { 'client': client }
        self.render(vars, 'clientdebtsprintdossier.html')

class ClientDebtsCloseDossier(BaseHandler):
    """Show all debts for a creditor"""
    def get(self, client=None):
        if not client:
            client = self.user
        else:
            client = models.Client.get(client)
        client.close()
        logging.error("We should redirect to some page, but I dont know which")

class OrganisationNew(BaseHandler):
    def get(self):
        form1 = forms.SocialWorkForm(prefix='f1')
        form2 = forms.SocialWorkerForm(prefix='f2')
        form1.title = 'Organisatie'
        form2.title = 'Contactpersoon'
        vars = { 'forms': [form1, form2] , 'title': 'Registreer Hulpverleningsorganisatie'}
        self.render(vars, 'form.html')

    def post(self):
        # Read form variables and put the new user in the database
        photo = self.request.get('f2-photo')
        form1 = forms.SocialWorkForm(self.request.POST, prefix='f1')
        form2 = forms.SocialWorkerForm(self.request.POST, prefix='f2')
        form1.title = 'Organisatie'
        form2.title = 'Contactpersoon'
        if form1.is_valid():
            organisation = form1.save(commit=False)
            organisation.put()
            the_user = form2.save(commit=False)
            the_user.set_password(form2.cleaned_data['password1'])
            the_user.organisation = organisation
            # FIXME: we should have an intermediate step to
            # retrieve the crop data for the image.
            # Size should be approximately 80x80 pixels

            if photo:
                # Resize the image
                image = images.Image(image_data=photo)
                the_user.photo = db.Blob(photo)

            the_user.put()
            session = get_current_session()
            if session.is_active():
                session.terminate()
            session['user'] = the_user
            self.redirect('/organisation/employees')
        else:
            #path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            vars = { 'forms': [form1, form2] , 'title': 'Registreer Hulpverleningsorganisatie'}
            self.render(vars, 'form.html')


class OrganisationEmployeesList(BaseHandler):
    def get(self):
        user = self.user
        organisation = user.organisation
#        employees = [ employee for employee in organisation.employees if employee.key != user.key ]
        employees = organisation.employees

        vars = { 'user': user, 'organisation': organisation, 'employees': employees }
        self.render(vars, 'listemployees.html')

    def post(self):
        action = self.request.get('action')
        if action == 'Create':
            self.redirect('/organisation/employees/add')
        elif action == 'Delete':
            for key_name in self.request.get_all('selected'):
                worker = models.SocialWorker.get_by_key_name(key_name)
                worker.delete()
            self.redirect('/organisation/employees')
        else:
            raise Exception('Invalid action %s' % action)


class Photo(BaseHandler):
    def get(self, key, original=False):
        """Return the photo for employee with KEY"""
        employee = models.SocialWorker.get(key)
        if (employee and employee.photo):
            self.response.headers['Content-Type'] = 'image/jpeg'
            if original and not employee.original_photo:
                logging.error("No original")

            if original and employee.original_photo:
                self.response.out.write(employee.original_photo)
            else:
                self.response.out.write(employee.photo)
        else:
            # TODO:
            self.redirect('/images/nopassphoto.gif')


class OrganisationEditEmployee(BaseHandler):
    """Create or edit an existing employee"""
    def get(self, key=None):
        user = self.user
        organisation = user.organisation
        if key:
            employee = models.SocialWorker.get(key)
            form = forms.SocialWorkerForm(instance=employee)
        else:
            form = forms.SocialWorkerForm()
        vars = { 'forms': [form] }

        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.render(vars, 'form.html')


    def post(self, key=None):
        # Read form variables and put the new user in the database
        user = self.user
        organisation = user.organisation
        if key:
            instance = models.SocialWorker.get(key)
            form = forms.SocialWorkerForm(self.request.POST, instance=instance)
        else:
            form = forms.SocialWorkerForm(self.request.POST)

        photo = self.request.get('photo')
        if form.is_valid():
            employee = form.save(commit=False)
            # FIXME: this password code can happen in the form class
            employee.set_password(form.cleaned_data['password1'])
            employee.organisation = organisation
            if photo:
                image = images.Image(image_data=photo)
                employee.photo = db.Blob(photo)
            employee.put()
            self.redirect('/organisation/employees')
            """
            if image.height != 80 and image.width != 80:
                self.redirect('/organisation/employees/resize/%s' % employee.key())
            else:
                self.redirect('/organisation/employees')
            """
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            vars = { 'forms': [form], 'title': 'Registreer'}
            self.render(vars, 'form.html')

class OrganisationEmployeeResize(BaseHandler):
    def get(self, key):
        worker = models.SocialWorker.get(key)
        vars = { 'worker': worker }
        self.render(vars, 'resize.html')

    def post(self, key):
        #self.response.headers['Content-Type'] = 'image/jpeg'
        self.response.headers['Content-Type'] = 'text/plain'
        x1 = float(self.request.get('x'))
        x2 = float(self.request.get('x2'))
        y1 = float(self.request.get('y'))
        y2 = float(self.request.get('y2'))

        worker = models.SocialWorker.get(key)
        vars = { 'worker': worker }
        if not worker.original_photo:
            worker.original_photo = db.Blob(worker.photo)
        image = images.Image(image_data=worker.original_photo)
        image.crop( x1 / image.width,
                    y1 / image.height,
                    x2 / image.width,
                    y2 / image.height )

        image = image.execute_transforms(output_encoding=images.JPEG)
        worker.photo = image
        worker.put()
        self.redirect('/organisation/employees')

        #self.dump()

class OrganisationZipcodes(BaseHandler):
    """TODO:"""
    def get(self):
        session = get_current_session()
        user = session.get('user')
        zipcodes = ','.join(user.organisation.zipcodes)
        vars = { 'user': user , 'zipcodes': zipcodes}
        self.render(vars, 'selectzipcodes.html')

    def post(self):
        zipcodes = self.request.get('zipcodes')
        zipcodes = zipcodes.replace(' ', '')
        zipcodes = zipcodes.split(',')
        user = self.user
        user.organisation.zipcodes = zipcodes
        user.organisation.put()
        self.redirect(self.request.url)


class Todo(BaseHandler):
    def get(self):
        self.response.out.write("TODO: URL is valid, but not implemented")


class ResetPassword(BaseHandler):
    def get(self, step=None):
        token = self.request.get('token')
        userid = self.request.get('userid')
        vars = {'token': token, 'userid': userid}

        if not step:
            template = 'resetpasswd.html'
        elif step == 'confirm':
            template = 'confirmreset.html'
        self.render(vars, template)

    def post(self, step=None):
        # TODO: generate a new password:
        #   Communicate this via SMS, e-mail or account manager.
        userid = self.request.get('userid')
        token = self.request.get('token')
        password1 = self.request.get('password1')
        password2 = self.request.get('password2')

        user_key = db.Key.from_path("User", userid)
        user = models.User.get(user_key)
        if not token:
            token = user.make_token()
            # FIXME: instead of writing this token
            # we should either send it to an e-mail address
            # or send it to SMS.
            path = os.path.join(os.path.dirname(__file__), 'brieven', 'reset-wachtwoord.html')
            vars = {}
            vars['self'] = self
            vars['userid'] = userid
            vars['token'] = token
            vars['message'] = 'Er is een e-mail verstuurd naar uw account met daarin een code. Met deze code kunt u uw wachtwoord opnieuw instellen.'
            text = template.render(path, vars)

            mail.send_mail(sender="No reply <hans.then@gmail.com>",
                           to="<h.then@pythea.nl>",
                           subject="U heeft een nieuw wachtwoord aangevraagd op schuldendossier.nl",
                           body=text)

#            self.render({'message': 'Er is een e-mail verstuurd naar uw e-mail account met instructies hoe u uw wachtwoord kunt resetten. %s' % token},
#                         'message.html')
            logging.info("Resetting password: token = %s" % token)
            del vars['token']
            self.render(vars, 'confirmreset.html')

        else:
            if user.check_token(token):
                if not password1 or password1 != password2:
                    self.render({'message': 'U heeft geen geldig wachtwoord ingevuld'},
                                 'message.html')
                else:
                    user.set_password(password1)
                    user.put()
                    self.session['user'] = user
                    self.redirect(user.start_page())
            else:
                self.render({'message': 'Uw heeft een ongeldig token ingevuld'},
                             'message.html')

class Logout(BaseHandler):
    def get(self):
        redirect = self.request.get("redirect")
        if self.session.is_active():
            self.session.terminate()
        self.response.set_status(301)
        if redirect:
            self.response.headers['Location'] = redirect
        else:
            self.response.headers['Location'] = "/"
        self.response.clear()

class Login(BaseHandler):
    def get(self):
    	vars = { 'user': self.user }
        self.render(vars, 'login.html')

    def post(self):
        userid = self.request.get('userid')
        passwd = self.request.get('password')
        session = get_current_session()
        if session.is_active():
            session.terminate()
        try:
            user = models.User.get_by_key_name(userid)
            if user and user.authenticate(passwd):
                session['user'] = user
                #self.redirect(user.start_page())
                self.redirect("/#"+user.start_page())
            else:
                #vars = { 'message': 'Gebruikersnaam of wachtwoord is ongeldig.' }
                #self.render(vars, 'login.html')
                self.redirect("/?message=Gebruikersnaam of wachtwoord is ongeldig")
        except Exception, e:
            logging.info("Error, probably user not found.")
            self.response.out.write(e)


class Session(BaseHandler):
    def get(self):
    	session = get_current_session()
    	user = session.get('user')
    	vars = { 'user': user }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'login.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'session.html')


class EmployeeViewCase(BaseHandler):
    def get(self, client, creditor=None):
        client = models.Client.get(client)
        base_url = '/employee/cases/view/%s' % client.key()
        if not creditor:
            creditor = client.creditors.get()
            self.redirect("%s/creditors/%s" % (self.request.url, creditor.key().id()))
        else:
            creditor = models.CreditorLink.get_by_id(int(creditor))
        annotations = creditor.annotations.order('-entry_date').run(limit=3)
        vars = { 'client' : client,
                 'base_url': base_url,
                 'annotations': annotations,
                 'creditor': creditor }
        self.render(vars, 'clientdebts.html')

class EmployeeViewCaseDetails(BaseHandler):
    def get(self, client, creditor):
        client = models.Client.get(client)
        creditor = models.CreditorLink.get_by_id(int(creditor))
        form = forms.DebtForm()
        selected = self.request.get('selected')
        if selected:
            selected = models.Creditor.get_by_id(int(selected))
        vars = { 'client': client,
                 'creditor': creditor,
                 'selected': selected,
                 'form': form }
        if creditor.creditor.is_collector:
            self.render(vars, 'clientdebtsview_collector.html')
        else:
            self.render(vars, 'clientdebtsview.html')

    def post(self, client, creditor):
        user = self.get_user()
        client = models.Client.get(client)
        form = forms.DebtForm(self.request.POST)
        creditor = models.CreditorLink.get_by_id(int(creditor))
        selected = self.request.get('selected')
        if selected:
            selected = models.Creditor.get_by_id(int(selected))
        else:
            selected = None
        if form.is_valid():
            new_debt = form.save(commit=False)
            new_debt.creditor = creditor
            if creditor.creditor.is_collector:
                new_debt.collected_for = selected
            else:
                new_debt.collector = selected
            new_debt.put()
            url = urlparse.urlsplit(self.request.url)
	    self.redirect(url.path)
        else:
            vars = { 'user': user,
                     'client': client,
                     'creditor': creditor,
                     'selected': selected,
                     'form': form }
            if creditor.creditor.is_collector:
                self.render(vars, 'clientdebtsview_collector.html')
            else:
                self.render(vars, 'clientdebtsview.html')


class EmployeeViewCaseCreditorActions(BaseHandler):
    """Show details for a CreditorLink"""
    def get(self, client, creditor):
        user = self.user
        client = models.Client.get(client)
        creditor = models.CreditorLink.get_by_id(int(creditor))
        vars = { 'user': user,
                 'client': client,
                 'creditor': creditor }
        self.render(vars, 'clientdebtscreditoractions.html')

    def post(self, client, creditor):
        user = self.user
        creditor = models.CreditorLink.get_by_id(int(creditor))
        text = self.request.get('text')
        annotation = models.Annotation(subject=creditor, author=user, text=text)
        annotation.put()
        self.redirect(self.request.url)

class EmployeeCasesList(BaseHandler):
    def get(self):
        clients = models.Client.all()
        clients.filter('state !=', 'FINISHED')
        vars = {
                 'clients' : clients }

        self.render(vars, 'employeecaseslist.html')

    def post(self):
        self.get()

class EmployeeApprove(BaseHandler):
    def get(self, client):
        client = models.Client.get_by_key_name(client)
        vars = { 'client' : client }
        self.render(vars, 'employeeapprove.html')

    def post(self, client):
        client = models.Client.get_by_key_name(client)
        for creditor in client.creditors:
            # send mail to the creditor (or the Bailiff for this creditor)
            creditor.send_email()
            creditor.put()
            pass
        client.approve()
        message = 'We zouden hier mails moeten versturen naar crediteuren, maar ik heb nog een voorbeeldbrief nodig. Hans'
        vars = { 'client' : client,
                 'message' : message }
        self.render(vars, 'message.html')


class AdminInfo(BaseHandler):
    def get(self):
        template = self.request.get('template')
        path = self.request.get('path')
        screen = models.Screen.get_by_key_name("%s@%s" % (template, path))
        vars = { 'template': template, 'path': path, 'screen': screen }
        self.render(vars, 'admin.html')

    def post(self):
        text = self.request.get('text')
        design = self.request.get('design')
        template = self.request.get('template')
        path = self.request.get('path')
        screen = models.Screen.get_by_key_name("%s@%s" % (template, path))
        if design:
            screen.design = db.Blob(design)
            screen.put()
        annotation = models.Annotation(subject=screen, admin=self.admin.nickname(), text=text)
        annotation.put()
        self.redirect(self.request.url)

class AdminBecome(BaseHandler):
    def get(self, client = None):
        if not client:
            clients = models.User.all()
            vars = { 'clients' : clients }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'adminbecomeclients.html')
            self.response.out.write(template.render(path, vars))
        else:
            client = urllib.unquote(client)
            logging.debug(client)
            user = models.User.get_by_key_name(client)
            if not user:
                self.redirect('/admin/become')
            else:
                start_page = user.start_page()
                logging.debug(start_page)
                session = get_current_session()
                if session.is_active():
                    session.terminate()
                session['user'] = user
                self.redirect(start_page)

class AddCompany(BaseHandler):
    def get(self):
	"""Show a form to enter a new creditor"""
	form = forms.CreditorForm(self.request.POST)
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        """Add the new creditor"""
        form = forms.CreditorForm(self.request.POST)
        if form.is_valid():
            creditor = form.save(commit=False)
            creditor.expand()
            creditor.put()
            self.redirect(self.request.url)
        else:
            vars = { 'forms': [form] }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            self.response.out.write(template.render(path, vars))


class AddCategory(BaseHandler):
    def get(self):
        """Show a list of existing categories"""
        form = forms.CategoryForm(self.request)
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        """Add a new category"""
        form = forms.CategoryForm(self.request)
        if form.is_valid():
            category = form.save(commit=True)
            self.redirect(self.request.url)
        else:
            vars = { 'forms': [form] }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            self.response.out.write(template.render(path, vars))
            # path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
            # vars = { 'form': form }
            # self.response.out.write(template.render(path, vars))


class ShowCategories(BaseHandler):
    def get(self):
         categories = Category.all()
         for category in categories:
             self.response.out.write(category.label + '<br>')


class EnterCreditors(BaseHandler):
    """Does not appear to be in use"""
    def get(self):
        """Show a list of possible creditors"""
        session = get_current_session()
        user = session.get('user')
        vars = {
                 'user': user, }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientcreditors.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        """Write the selected creditors to the database"""
        session = get_current_session()
        user = session.get('user')
        for creditor in user.creditors:
            amount = decimal.Decimal(self.request.get(str(creditor.key().id())))
            if creditor.estimated_amount != amount:
                creditor_estimated.amount = amount
                creditor.put()
                logging.info('Really different, write to database.')
            else:
                logging.info('Not really all that different, do not write to database.')

        self.redirect('/debts')

class ShowCreditors(BaseHandler):
    def get(self):
        """Show a list of available creditors
        """
        creditors = list(models.Creditor.all())
        creditors.reverse()

        self.render({'creditors':creditors }, "admincreditors.html")

class AdminCreditorEdit(BaseHandler):
    def get(self, creditor = None):
	"""Show a form to enter a new creditor"""
        if creditor:
            creditor = models.Creditor.get_by_id(int(creditor))
            form = forms.CreditorForm(instance=creditor)
        else:
            form = forms.Form()
        vars = { 'forms': [form] }
        self.render(vars, 'form.html')

    def post(self, creditor=None):
        """Add the new creditor"""
        if creditor:
            creditor = models.Creditor.get_by_id(int(creditor))
            form = forms.CreditorForm(self.request.POST, instance=creditor)
            expand = True
        else:
            form = forms.CreditorForm(self.request.POST)
            expand = False

        if form.is_valid():
            creditor = form.save(commit=False)
            if expand: creditor.expand()
            creditor.put()
            self.redirect(self.request.url)
        else:
            vars = { 'forms': [form] }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')

class Initialize(BaseHandler):
    def get(self):
        taskqueue.add(url='/task/init')

class Handle404(BaseHandler):
    def get(self, url):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.set_status(404, "Oops")
        self.response.out.write("404: %s bestaat niet" % url)

    def post(self, url):
        self.get(url)

class Test2(BaseHandler):
    """I use this to test new code"""
    def get(self):
        """Show the test response"""
        user = self.get_user()
        self.response.out.write(self.request.accept)

class Test(BaseHandler):
    """I use this to test new code"""
    def get(self, args = "http://www.ing.nl"):
        """Show the test response"""

        self.render({}, 'test.html')


    def post(self):
        """Testing the code to resize a passphoto"""
        #self.response.headers['Content-Type'] = 'image/jpeg'
        self.response.headers['Content-Type'] = 'text/plain'
        x1 = float(self.request.get('x'))
        x2 = float(self.request.get('x2'))
        y1 = float(self.request.get('y'))
        y2 = float(self.request.get('y2'))

        with open('nopassphoto.gif') as file:
            image = images.Image(image_data=file.read())
        image.crop( x1 / image.width,
                    y1 / image.height,
                    x2 / image.width,
                    y2 / image.height )

        image = image.execute_transforms(output_encoding=images.JPEG)
        self.response.out.write(image)

        #self.dump()

class TaskInitialize(BaseHandler):
    def get(self):
        logging.info(str(self.request.url))
        taskqueue.add(url='/admin/init')

    def post(self):
        """Background task to initialize the database with a list of clients and creditors"""
        try:
            client = models.Client(key_name='hans.then', username='clientXX', first_name='client',
                                   last_name='XX', email='hans.then@gmail.com',
                                   address='Rochussenstraat 347a', zipcode='3023 HE',
                                   city='Rotterdam', mobile='+31634751204')
            client.set_password('XX')
            client.put()
        except:
            logging.info('Error creating client')

        try:
            contact = models.SocialWorker(key_name='hans.then@gmail.com', username='contact XX', first_name='SMDD contact',
                                          last_name='XX', email='hans.then@gmail.com')
            contact.set_password('XX')
            organisation = models.SocialWork(key_name='SMDD', display_name='SMDD', website='http://www.smdd.nl',
                                               email='info@smdd.nl', address='Havenstraat 80',
                                               zipcode='2300', city='Rotterdam', contact=contact)
            organisation.put()
            contact.organisation = organisation
            contact.put()
            worker = models.SocialWorker(key_name='h.then@gpythea.nl', username='medewerker XX', first_name='SMDD MW',
                                          last_name='XX', email='hans.then@gmail.com', organisation=organisation)
            contact.set_password('XX')
            worker.put()

        except Exception, e:
            logging.info('Error creating organisation')
            logging.info(e)

        with open('schuldeisers.txt') as file:
            for line in file:
                website, display_name = line.strip().split(None,1)
                if display_name.find('[') != -1:
                     display_name, categories = display_name.split('[',1)
                     categories = categories.strip(']')
                     categories = categories.split(',')
                else:
                     categories = []
                q = db.Query(models.Organisation, keys_only = True)
                q.filter('display_name =', display_name)
                org = q.fetch(1)
                if org:
                    logging.info('%s,%s Already done' % (website, display_name))
                    continue
                else:
                    logging.info('%s,%s' % (website, display_name))
                    is_collector = False
                    if website.startswith('>'):
                        is_collector = True
                        categories.append('Deurwaarder')
                        website = website[1:]
                    website = 'http://' + website
                    creditor = models.Creditor(website=website,
                                               is_collector=is_collector,
                                               display_name=display_name, categories=categories)
                    try:
                        creditor.expand()
                        creditor.put()
                    except Exception, e:
                        logging.info( "Failed to put %s %s" % (display_name, e) )


        with open('categories.txt') as file:
            for line in file:
                try:
                    label, question = line.strip().split('|', 1)
                    label = label.strip()
                    question = question.strip()
                    category = models.Category(key_name=label, label=label, question=question)
                    category.put()
                except Exception, e:
                    logging.info( "Failed to put %s %s" % (label, e) )

application = webapp.WSGIApplication([
# Anonymous
  (r'/', Main),
  (r'/login', Login),
  (r'/logout', Logout),
  (r'/reset', ResetPassword),
  (r'/reset/(confirm)', ResetPassword),

# Admin functions
  (r'/admin/init', TaskInitialize),
  (r'/admin/screens', Screens),
#  (r'/finished', Finished),
  (r'/admin/company/new', AddCompany),
  (r'/admin/category/new', AddCategory),
#  (r'/addemployees', AddEmployees),
  (r'/admin/category/list', ShowCategories),
  (r'/admin/creditor/list', ShowCreditors),
  (r'/admin/creditor/edit/(.*)', AdminCreditorEdit),
  (r'/admin/test', Test),
  (r'/admin/test/(.*)', Test),
  (r'/admin/test2', Test2),
  (r'/admin/become/client/(.*)', AdminBecome),
  (r'/admin/info', AdminInfo),
  (r'/admin/become', AdminBecome),

# Background tasks
#  (r'/task/init', TaskInitialize),

# The register client use case
  (r'/client/register', ClientEdit),
  (r'/client/info', ClientEdit),
  (r'/client/register/contact', ClientContact),
  (r'/client/creditors/category/(.*)/new', ClientAddCreditor),
  (r'/client/creditors', ClientSelectCreditors),
  (r'/client/creditors/category/(.*)', ClientSelectCreditors),
  (r'/client/creditors/validate', ClientValidate),
  (r'/client/register/previewletter/(.*)', ClientRegisterPreviewLetter),
  (r'/client/register/printletter/(.*)', ClientRegisterPrintLetter),
  (r'/client/register/submitted', ClientSubmitted), # FIXME: this is more of a confirmation message than a
                                           # real GET/POST
# The register organisation use case
  (r'/organisation/register', OrganisationNew),
  (r'/organisation/employees', OrganisationEmployeesList),
  (r'/organisation/register/zipcodes', OrganisationZipcodes), #FIXME:
  (r'/organisation/employees/add', OrganisationEditEmployee),
  (r'/organisation/employees/edit/(.*)', OrganisationEditEmployee),
  (r'/organisation/employees/resize/(.*)', OrganisationEmployeeResize),
  (r'/employee/photo/(.*)/(original)/(really)', Photo),
  (r'/employee/photo/(.*)/(original)', Photo),
  (r'/employee/photo/(.*)', Photo),

# The clients edit debts use case
  (r'/client/debts', ClientDebts),
  (r'/client/debts/list', ClientDebts),
  (r'/client/debts/view/(.*)', ClientDebtsView),
  (r'/client/debts/print', ClientDebtsPrintDossier),
  (r'/client/debts/close', ClientDebtsCloseDossier),
  (r'/client/debts/creditor/select', ClientDebtsSelectCreditor),
  (r'/client/debts/creditor/select/(.*)', ClientDebtsSelectCreditor),
  (r'/client/debts/creditor/(.*)/actions', ClientDebtsCreditorActions),
  (r'/client/debts/creditor/(.*)', ClientDebts),

# Several employee use cases
  (r'/employee/cases', EmployeeCasesList),
# The shared screens between client and employee
  (r'/employee/cases/view/(.*)/view/(.*)', EmployeeViewCaseDetails), # => /client/debts/view
  (r'/employee/cases/view/(.*)/print', ClientDebtsPrintDossier), # => /client/debts/print
  (r'/employee/cases/view/(.*)/creditor/(.*)', EmployeeViewCase),
  (r'/employee/cases/view/(.*)/creditor/(.*)/actions', EmployeeViewCaseCreditorActions),
  (r'/employee/cases/view/(.*)', EmployeeViewCase), # => /client/debts
#  (r'/client/debts/creditor/select', ClientDebtsSelectCreditor),
#  (r'/client/debts/creditor/select/(.*)', ClientDebtsSelectCreditor),
#  (r'/client/debts/creditor/(.*)/actions', ClientDebtsCreditorActions),

# Catch all
  (r'/(.*)', Handle404),
], debug=True)

def main():
    run_wsgi_app(application)

def handle_404(request, response, exception):
    logging.exception(exception)
    response.write('Oeps! Deze pagina bestaat niet!')
    response.set_status(404)

if __name__ == '__main__':
    main()

