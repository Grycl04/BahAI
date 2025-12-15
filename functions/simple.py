from firebase_functions import https_fn 
from firebase_admin import initialize_app 
 
initialize_app() 
 
@https_fn.on_request() 
def simpletest(req): 
    return https_fn.Response('Python test working') 
