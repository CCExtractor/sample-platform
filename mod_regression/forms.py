from flask_wtf import FlaskForm
from wtforms import Form, StringField, SubmitField
from wtforms.validators import DataRequired

class AddCategoryForm(FlaskForm):
    """
    Flask form to Add Category
    """
    category_name = StringField('Category Name', [DataRequired(message="Category name can't be empty")])
    category_description = StringField('Description')
    submit = SubmitField("Add Category")
