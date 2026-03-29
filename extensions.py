from flask_pymongo import PyMongo
from flask_mail import Mail
from flask_session import Session

mongo = PyMongo()
mail = Mail()
sess = Session()
