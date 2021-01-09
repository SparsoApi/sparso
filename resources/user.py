import traceback
import time

import bcrypt
from flask import make_response, render_template
from flask_jwt_extended import (
                                create_access_token, create_refresh_token,
                                fresh_jwt_required, get_jwt_identity,
                                get_raw_jwt, jwt_refresh_token_required,
                            )
from flask_restful import Resource, request
from marshmallow import ValidationError
from werkzeug.security import safe_str_cmp

from db import db
from libs.mailgun import MailgunException
from models.user import TokenBlacklist, UserModel
from phone import Country
from schemas.user import (
                            UserSchema, UserLoginSchema, UsernameSchema,
                            EmailSchema, PasswordSchema, LocationSchema
                        )
from schemas.user_confirm import UserConfirmationSchema
from models.user_confirm import UserConfirmationModel

USER_NOT_FOUND = "User not Found!"
USER_DELETED = "User {} has been deleted"
EMAIL_TAKEN = "{} has been taken by another user"
EMAIL_DOES_NOT_EXIST = "{} does not exist in our database"
USER_CREATED = "Account created for {}. check your email for procedures to activate your account."
INTERNAL_SERVER_ERROR = "We are having some issues with our servers at the moment. Please come back later" 
NOT_ACTIVATED = "Account for {} has not yet been activated. Click the link sent to your email to activate your account."
INCORRECT_EMAIL_OR_PASSWORD = "Is this your email or password?"
LOGGED_OUT = "You have been logged out."
CONFIRMATION_TOKEN_NOT_FOUND = "Confirmation token not found in database."
EXPIRED_TOKEN = "Expired token, request for a new token"
TOKEN_ALREADY_CONFIRMED = "This token has already been confirmed"
RESEND_SUCCESSFULL = "Resend Successful"
RESEND_FAILED = "Resend Failed"
USER_DETAILS_REQUIRED = "Please fill in all fields marked with *"
EMAIL_UPDATED = "Click on the link sent to the email address provided to update your account"
ACCOUNT_UPDATED = "Your account has been successfully updated"

user_schema = UserSchema(load_only=('password', 'id',))
login_schema = UserLoginSchema(load_only=('password'))


class User(Resource):
 
    @classmethod
    @jwt_refresh_token_required
    def get(cls, name):
        get_user = UserModel.find_user_by_name(name) 
        if not get_user:
            return {'message': USER_NOT_FOUND }, 404
        return user_schema.dump(get_user), 200 


class DeleteUser(Resource):
    @classmethod
    @fresh_jwt_required
    def delete(cls):
        user_identity = get_jwt_identity()
        user = UserModel.find_user_by_email(user_identity)
        if not user:
            return {"Message": USER_NOT_FOUND }, 400
        user.delete_from_db()
        return {"message": USER_DELETED.format(user.username)},200


class UpdateUserUsername(Resource):
    @fresh_jwt_required
    def put(self):
        username_schema = UsernameSchema()
        user_identity = get_jwt_identity() 
        current_user = UserModel.find_user_by_email(user_identity) 
        
        if current_user:
            user = request.get_json()
            try:
                get_user = username_schema.load(user)
            except ValidationError as err:
                return err.messages, 404

            current_user.username = get_user["username"]

            db.session.commit()

            return {"message": ACCOUNT_UPDATED}, 200
        return {"message": USER_NOT_FOUND}, 404


class UpdateUserEmail(Resource):
    @fresh_jwt_required
    def put(self):
        email_schema = EmailSchema()
        user_identity = get_jwt_identity() 
        current_user = UserModel.find_user_by_email(user_identity) 
        
        if current_user:
            user = request.get_json()
            try:
                get_user = email_schema.load(user)
            except ValidationError as err:
                return err.messages, 404

            try:
                current_user.email = get_user["email"]

                if get_user['email'] == current_user.email or UserModel.find_user_by_email(get_user['email']):
                    return {"message": EMAIL_TAKEN.format(get_user['email'])}, 400

                new_confirmation = UserConfirmationModel(current_user.id)
                new_confirmation.save_to_db()
                current_user.send_email()

                db.session.commit()
                return {"message": EMAIL_UPDATED}, 200

            except (MailgunException, traceback.print_exc()) as err:
                return {'message': str(err)}, 500

        return {"message": USER_NOT_FOUND}, 404


class UpdateUserPassword(Resource):
    @fresh_jwt_required
    def put(self):
        password_schema = PasswordSchema()
        user_identity = get_jwt_identity() 
        current_user = UserModel.find_user_by_email(user_identity) 
        
        if current_user:
            user = request.get_json()
            try:
                get_user = password_schema.load(user)
            except ValidationError as err:
                return err.messages, 404

            current_user.password = psw.generate_password_hash(get_user["password"])

            db.session.commit()

            return {"message": ACCOUNT_UPDATED}, 200
        return {"message": USER_NOT_FOUND}, 404


class UpdateUserLocation(Resource):
    @fresh_jwt_required
    def put(self):
        location_schema = LocationSchema()
        user_identity = get_jwt_identity() 
        current_user = UserModel.find_user_by_email(user_identity) 
        
        if current_user:
            user = request.get_json()
            try:
                get_user = location_schema.load(user)
            except ValidationError as err:
                return err.messages, 404

            current_user.country = Country.get_country_name(Country, get_user['country'])
            country_region = Country.get_country_region(Country)
            current_user.phone_number = Country.get_user_phonenumber(Country, get_user["phone_number"])
            current_user.state = Country.get_states(Country, get_user['state'])
            current_user.city = Country.get_city(Country, get_user['city'])
            
            db.session.commit()

            return {"message": ACCOUNT_UPDATED}, 200
        return {"message": USER_NOT_FOUND}, 404


class UserRegister(Resource):
    @classmethod
    def post(cls):
        user_details = request.get_json()

        try:
            user = user_schema.load(user_details)
        except ValidationError as err:
            return err.messages, 404

        if UserModel.find_user_by_email(user['email']):
            return {"message": EMAIL_TAKEN.format(user['email'])}, 404

        try:
            c_user = UserModel(**user)
            c_user.save_to_db()
            confirmation = UserConfirmationModel(c_user.id)
            confirmation.save_to_db()
            c_user.send_email()
            return {"message": USER_CREATED.format(c_user.username)}, 200

        except MailgunException as e:
            c_user.delete_from_db()
            return {"message": str(e)}, 500

        except EnvironmentError:
            traceback.print_exc()
            c_user.delete_from_db()
            return {"message": INTERNAL_SERVER_ERROR}, 500


class UserLogin(Resource):
    @classmethod
    def post(cls):
        get_user_details = request.get_json()
        user = login_schema.load(get_user_details)

        get_user_from_db = UserModel.find_user_by_email(get_user_details['email'])

        if get_user_from_db and bcrypt.checkpw(user['password'], get_user_from_db.password):
            confirmation = get_user_from_db.recent_confirmation
            if confirmation and confirmation.confirmed:
                access_token = create_access_token(identity=get_user_from_db.email,fresh=True)
                refresh_token = create_refresh_token(get_user_from_db.email)

                return {
                    "Access_Token": access_token,
                    "Refresh_Token": refresh_token
                }, 200

            return {"message": NOT_ACTIVATED.format(get_user_from_db.email)}, 404
        return {"message": INCORRECT_EMAIL_OR_PASSWORD}, 400


class UserLogout(Resource):
    @classmethod
    @jwt_refresh_token_required
    def post(cls):
        jti = get_raw_jwt()['jti']
        try:
            revoked_token = TokenBlacklist(jti=jti)
            revoked_token.add()
            return {"message": LOGGED_OUT}, 200
        except EnvironmentError:
            return {"message": INTERNAL_SERVER_ERROR}, 500


class TokenRefresh(Resource):
    @classmethod
    @jwt_refresh_token_required
    def post(cls):
        current_user = get_jwt_identity()
        new_token = create_access_token(identity=current_user, fresh=False)
        return {"access_token": new_token}, 200


class UserConfirm(Resource):

    def get(self, confirmation_id: str):

        confirmation = UserConfirmationModel.find_by_id(confirmation_id)

        if not confirmation:
            return{'message': CONFIRMATION_TOKEN_NOT_FOUND}, 404

        if confirmation.token_expires_at < int(time.time()):
            return{'message': EXPIRED_TOKEN}, 404

        if confirmation.confirmed:
            return{'message': TOKEN_ALREADY_CONFIRMED}, 404

        confirmation.confirmed = True
        confirmation.save_to_db()
        headers = {"Content-Type": "text/html"}
        return make_response(
            render_template("confirmation_page.html", email=confirmation.user.email), 200, headers
        )


class TestConfirmation(Resource):    # Test Class
    @classmethod
    def get(cls, user_id):
        user = UserModel.find_user_by_id(user_id)

        if not user:
            return {'message': USER_NOT_FOUND}, 404
        
        return (
            {
                "Current Time" : int(time.time()),
                "confirmation" : [
                    UserConfirmationSchema.dump(each)
                    for each in user.confirmed.order_by(UserConfirmationModel.token_expires_at)
                ],
            },
            200,
        )

    @classmethod
    def post(cls, user_id):     # Resend_confirmation_token resource
        user = UserModel.find_user_by_id(user_id)

        if not user:
            return {'message': USER_NOT_FOUND}, 404

        try:
            confirmation = user.recent_confirmation
            if confirmation:
                if confirmation.confirmed:
                    return {"message": TOKEN_ALREADY_CONFIRMED}, 404
                confirmation.force_expire()

            new_confirmation = UserConfirmationModel(user_id)
            new_confirmation.save_to_db()
            user.send_email()
            return {"message": RESEND_SUCCESSFULL}, 200

        except MailgunException as e:
            return {"message": str(e)}, 500
        except EnvironmentError:
            traceback.print_exc()
            return{"message": RESEND_FAILED}, 500
