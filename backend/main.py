from flask import Flask
from flask_cors import CORS

from routes.orders import orders_bp
from routes.users import users_bp
from routes.tables import tables_bp
from routes.products import products_bp
from routes.orders_extra import orders_extra_bp
from routes.admin import admin_bp

app = Flask(__name__)
CORS(app)

app.register_blueprint(orders_bp)
app.register_blueprint(users_bp)
app.register_blueprint(tables_bp)
app.register_blueprint(products_bp)
app.register_blueprint(orders_extra_bp)
app.register_blueprint(admin_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
