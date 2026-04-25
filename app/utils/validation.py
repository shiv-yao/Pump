# Validation Utilities

"""
This module contains custom validators for plugin commands and requests.
"""

class Validator:
    @staticmethod
    def is_non_empty_string(value):
        if not isinstance(value, str) or not value:
            raise ValueError("Value must be a non-empty string.")
        return True

    @staticmethod
    def is_positive_integer(value):
        if not isinstance(value, int) or value <= 0:
            raise ValueError("Value must be a positive integer.")
        return True

    @staticmethod
    def is_valid_email(value):
        # Simple regex for email validation
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, value):
            raise ValueError("Value must be a valid email address.")
        return True
    
    @staticmethod
    def is_in_choices(value, choices):
        if value not in choices:
            raise ValueError(f"Value must be one of the following: {choices}")
        return True

# Example usage:
# try:
#     Validator.is_non_empty_string("")
# except ValueError as e:
#     print(e)