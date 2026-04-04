"""AWS Lambda handler using Mangum adapter.

To use this handler, install mangum:  ``pip install mangum``
Set the Lambda handler to ``backend.deploy.lambda_handler.handler``.
"""

from mangum import Mangum

from backend.app.main import app

handler = Mangum(app, lifespan="off")
