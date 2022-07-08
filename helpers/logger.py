"""
AutoPkg Runner: Log Helper Module


"""
def logger(message: str, indent:int = 0):
    """Format and output a message to console"""
    print("  "*indent, "==>", message)
