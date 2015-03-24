# -*- coding: utf-8 -*-

"""
    conpaas.core.expose
    ===================

    ConPaaS core: expose http methods.

    :copyright: (C) 2010-2013 by Contrail Consortium.
"""

exposed_functions_http_methods = {}
def expose(http_method):
    """
    This decorator simply stores the http_method for a given handler (exposed) function 
    in a global dictionary, namely exposed_functions_http_methods 
    """
    def decorator(func):
      exposed_functions_http_methods[id(func)] = http_method
      def wrapped(self, *args, **kwargs):
        return func(self, *args, **kwargs)
      return wrapped
    return decorator



# exposed_functions = {}

# def expose(http_method):
#     """
#     Exposes http methods methods.
    
#     :param func: Function to be exposed
#     :type conf: function    
#     :returns: A decorator to be used in the source code. 
    
#     """
#     def decorator(func):
#       if http_method not in exposed_functions:
#         exposed_functions[http_method] = {}
#       exposed_functions[http_method][func.__name__] = func
#       def wrapped(self, *args, **kwargs):
#         return func(self, *args, **kwargs)
#       return wrapped
#     return decorator
