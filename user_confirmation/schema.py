from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from models.user_confirmation import UserConfirmationModel


class UserConfirmationSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = UserConfirmationModel
        load_only = ("user",)
        include_fk = True
