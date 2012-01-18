from __future__ import with_statement
import os
import logging
import datetime
import pickle
import crypt
import decimal

from google.appengine.ext import db
from google.appengine.ext.db import polymodel
import wsgiref.handlers

class DecimalProperty(db.Property):
    data_type = decimal.Decimal

    def get_value_for_datastore(self, model_instance):
        value = super(DecimalProperty, self).get_value_for_datastore(model_instance)
        return str(value) if value != None else None

    def make_value_from_datastore(self, value):
        if value is None: return value
        return decimal.Decimal(value).quantize(decimal.Decimal('0.01'))

    def validate(self, value):
        value = super(DecimalProperty, self).validate(value)
        if value is None or isinstance(value, decimal.Decimal):
            return value
        elif isinstance(value, basestring):
            return decimal.Decimal(value)
        raise db.BadValueError("Property %s must be a Decimal or string." % self.name)

class User(polymodel.PolyModel):
    username = db.StringProperty()
    first_name = db.StringProperty()
    last_name= db.StringProperty()
    email = db.EmailProperty()
    password = db.ByteStringProperty()
    
    is_active = db.BooleanProperty()
    is_staff = db.BooleanProperty()
    is_superuser = db.BooleanProperty()
    
    last_login = db.DateTimeProperty()
    date_joined = db.DateTimeProperty()
    
    def set_password(self, password):
        self.password = crypt.crypt(password, os.urandom(2))

    def authenticate(self, password):
        return crypt.crypt(password, self.password) == self.password

    
# FIXME: Organisation also needs to be scoped to 
# a zipcode. E.g. woonbron delfshaven has a different mail address
# than woonbron ijsselmonde.
class Organisation(polymodel.PolyModel):
    display_name = db.StringProperty()
    icon = db.LinkProperty()
    website = db.LinkProperty()
    email = db.EmailProperty()

class SocialWork(Organisation):
    address = db.StringProperty()
    zipCode = db.StringProperty()
    city = db.StringProperty()
    zipcodes = db.StringListProperty()
    
    def accepts(self, zipcode):
        return True

class SocialWorker(User):
    organisation = db.ReferenceProperty(SocialWork, collection_name="employees")
    sysadmin = db.BooleanProperty()
    photo = db.BlobProperty()

    def set_sysadmin(worker, flag):
        if not self.sysadmin:
            raise Unauthorized
        else:
            worker.sysadmin = flag

class Client(User):
    address = db.StringProperty()
    zipcode = db.StringProperty()
    city = db.StringProperty()
    phone = db.PhoneNumberProperty()
    mobile = db.PhoneNumberProperty()
    state = db.StringProperty(default="NEW") # One of NEW, COMPLETED, APPROVED, DONE 
    completion_date = db.DateProperty()
    approval_date = db.DateProperty()
    archive_date = db.DateProperty() # ==> when the client is finished with entering his case file
    contact = db.ReferenceProperty(SocialWorker, collection_name="clients")

    def hasCreditor(self, creditor):
        for link in self.creditors:
            if link.creditor.key().id() == creditor.key().id():
                return True

    def addCreditor(self, creditor, amount=None):
        if not self.hasCreditor(creditor):
            link = CreditorLink(creditor=creditor, user=self, estimated_amount=amount)
            link.put()
    
    def removeCreditor(self, creditor):
        for link in self.creditors:
            if link.creditor.key().id() == creditor.key().id():
                link.delete()


    def complete(self):
        self.state = "COMPLETED"
        self.put()

    def approve(self):
        self.state = "APPROVED"
        self.put()

    def finish(self):
        self.state = "FINISHED"
        self.put()

    def reopen(self):
        self.state = "APPROVED" 
        self.put()

class Category(db.Model):
    label = db.StringProperty()

    def __str__(self):
        return self.label


class Creditor(Organisation):
    tags = db.StringListProperty()


class CreditorLink(db.Model):
    creditor = db.ReferenceProperty(Creditor)
    user = db.ReferenceProperty(Client, collection_name='creditors')
    estimated_amount = DecimalProperty(default=decimal.Decimal('0.00')) 
    approved = db.BooleanProperty()
    registration_date = db.DateProperty(auto_now_add=True)
    last_changed_date = db.DateProperty(auto_now=True)


class Debt(db.Model):
    creditor = db.ReferenceProperty(CreditorLink, collection_name='debts')
    collector = db.ReferenceProperty(Creditor)
    original_date = db.DateProperty()
    dossier_number = db.StringProperty()
    registration_date = db.DateProperty(auto_now_add=True)
    last_changed_date = db.DateProperty(auto_now=True)
    amount = DecimalProperty(default=decimal.Decimal('0.00')) 
    payment_amount = DecimalProperty(default=decimal.Decimal('0.00')) 


class Annotation(db.Model):
    subject = db.ReferenceProperty(db.Model, collection_name='annotation')
    tag = db.CategoryProperty()
    entry_date = db.DateProperty(auto_now_add=True)
    date = db.DateProperty()
    text = db.TextProperty()

