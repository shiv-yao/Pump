class CommandError(Exception):
    """Exception raised for errors in the command processing."""
    pass

class PluginError(Exception):
    """Exception raised for errors related to plugins."""
    pass

class ValidationError(Exception):
    """Exception raised for validation errors."""
    pass
