# ============================================================
# ApnaKhana - NGO Waste Food Management System
# Backend API
# Flask + MongoDB Atlas
# ============================================================

from flask import Flask, request, jsonify
from flask_cors import CORS

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from bson import ObjectId

from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv

from datetime import datetime, timezone, timedelta
import os
import smtplib
import secrets
import hashlib
from email.message import EmailMessage


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

CORS(app)


# ============================================================
# MONGODB CONFIGURATION
# ============================================================

MONGO_URI = os.getenv("MONGO_URI")

DB_NAME = os.getenv("DB_NAME", "apnaKhanaDB")


if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI is missing. Please check your backend/.env file."
    )


# ============================================================
# MONGODB CONNECTION
# ============================================================

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=10000,
    retryWrites=True
)

db = client[DB_NAME]


# ============================================================
# COLLECTIONS
# ============================================================

users_collection = db["users"]

donations_collection = db["donations"]

requests_collection = db["food_requests"]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def current_time():
    """
    Return current UTC time in ISO format.
    """
    return datetime.now(timezone.utc).isoformat()


def serialize_document(document):
    """
    Convert MongoDB document into JSON-safe dictionary.
    """

    if not document:
        return None

    document = dict(document)

    if "_id" in document:
        document["id"] = str(document["_id"])
        del document["_id"]

    return document


def serialize_documents(documents):
    """
    Convert multiple MongoDB documents into JSON-safe dictionaries.
    """

    return [
        serialize_document(document)
        for document in documents
    ]


def valid_object_id(value):
    """
    Check whether a value is a valid MongoDB ObjectId.
    """

    return ObjectId.is_valid(value)


# ============================================================
# BASIC ROUTE
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "success": True,
        "message": "ApnaKhana Backend is running!",
        "database": DB_NAME
    })


# ============================================================
# DATABASE TEST
# ============================================================

@app.route("/api/db-test", methods=["GET"])
def database_test():

    try:

        client.admin.command("ping", maxTimeMS=5000)

        return jsonify({
            "success": True,
            "message": "MongoDB connected successfully!",
            "database": DB_NAME
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": "MongoDB connection failed!",
            "error": str(e)
        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():

    try:

        client.admin.command("ping", maxTimeMS=5000)

        return jsonify({
            "success": True,
            "backend": "running",
            "database": "connected"
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "backend": "running",
            "database": "disconnected",
            "error": str(e)
        }), 500


# ============================================================
# USER REGISTER
# ============================================================

@app.route("/api/register", methods=["POST"])
def register():

    try:

        data = request.get_json(silent=True) or {}

        name = str(data.get("name", "")).strip()

        email = str(data.get("email", "")).strip().lower()

        password = str(data.get("password", "")).strip()

        role = str(data.get("role", "")).strip().lower()

        contact = str(
            data.get(
                "contact",
                data.get("phone", "")
            )
        ).strip()

        address = str(
            data.get(
                "address",
                data.get("location", "")
            )
        ).strip()

        # ----------------------------------------------------
        # NGO GPS LOCATION
        # ----------------------------------------------------
        # Register.jsx sends latitude/longitude only for NGO users.
        # These coordinates are stored in MongoDB and later used
        # by the Home / Nearby NGO pages to calculate distance.

        latitude = data.get("latitude")
        longitude = data.get("longitude")

        if role == "ngo":

            try:
                latitude = float(latitude)
                longitude = float(longitude)

                if not (-90 <= latitude <= 90):
                    raise ValueError("Invalid latitude.")

                if not (-180 <= longitude <= 180):
                    raise ValueError("Invalid longitude.")

            except (TypeError, ValueError):

                return jsonify({
                    "success": False,
                    "message": "Valid NGO location coordinates are required."
                }), 400


        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not name:

            return jsonify({
                "success": False,
                "message": "Name is required."
            }), 400


        if not email:

            return jsonify({
                "success": False,
                "message": "Email is required."
            }), 400


        if not password:

            return jsonify({
                "success": False,
                "message": "Password is required."
            }), 400


        if len(password) < 6:

            return jsonify({
                "success": False,
                "message": "Password must contain at least 6 characters."
            }), 400


        if not role:

            return jsonify({
                "success": False,
                "message": "Role is required."
            }), 400


        allowed_roles = [
            "donor",
            "ngo",
            "volunteer",
            "admin"
        ]

        if role not in allowed_roles:

            return jsonify({
                "success": False,
                "message": "Invalid role."
            }), 400


        # ----------------------------------------------------
        # CHECK EXISTING USER
        # ----------------------------------------------------

        existing_user = users_collection.find_one({
            "email": email
        })


        if existing_user:

            return jsonify({
                "success": False,
                "message": "Email already registered."
            }), 409


        # ----------------------------------------------------
        # CREATE USER
        # ----------------------------------------------------

        user_document = {

            "name": name,

            "email": email,

            "password": generate_password_hash(password),

            "role": role,

            "contact": contact,

            "address": address,

            # NGO location
            "latitude": latitude if role == "ngo" else None,
            "longitude": longitude if role == "ngo" else None,

            "createdAt": current_time(),

            "status": "Active"
        }


        result = users_collection.insert_one(
            user_document
        )


        return jsonify({

            "success": True,

            "message": "Registration successful.",

            "user": {

                "id": str(result.inserted_id),

                "name": name,

                "email": email,

                "role": role,

                "contact": contact,

                "address": address,

                "latitude": latitude if role == "ngo" else None,

                "longitude": longitude if role == "ngo" else None
            }

        }), 201


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Registration failed.",

            "error": str(e)

        }), 500
# ============================================================
# PRIVATE ADMIN LOGIN
# ============================================================

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


@app.route("/api/admin/login", methods=["POST"])
def admin_login():

    try:
        data = request.get_json(silent=True) or {}

        email = str(
            data.get("email", "")
        ).strip().lower()

        password = str(
            data.get("password", "")
        ).strip()

        # ----------------------------------------------------
        # CHECK ADMIN CREDENTIALS
        # ----------------------------------------------------

        if (
            not ADMIN_EMAIL
            or not ADMIN_PASSWORD
            or email != ADMIN_EMAIL.lower()
            or password != ADMIN_PASSWORD
        ):
            return jsonify({
                "success": False,
                "message": "Invalid administrator credentials."
            }), 401

        # ----------------------------------------------------
        # ADMIN LOGIN SUCCESS
        # ----------------------------------------------------

        return jsonify({
            "success": True,
            "message": "Administrator login successful.",
            "user": {
                "id": "private-admin",
                "name": "Administrator",
                "email": ADMIN_EMAIL,
                "role": "admin"
            }
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": "Admin login failed.",
            "error": str(e)
        }), 500

# ============================================================
# USER LOGIN
# ============================================================

@app.route("/api/login", methods=["POST"])
def login():

    try:

        data = request.get_json(silent=True) or {}

        email = str(
            data.get("email", "")
        ).strip().lower()

        password = str(
            data.get("password", "")
        ).strip()


        if not email or not password:

            return jsonify({

                "success": False,

                "message": "Email and password are required."

            }), 400


        # ----------------------------------------------------
        # FIND USER
        # ----------------------------------------------------

        user = users_collection.find_one({
            "email": email
        })


        if not user:

            return jsonify({

                "success": False,

                "message": "Invalid email or password."

            }), 401


        # ----------------------------------------------------
        # CHECK PASSWORD
        # ----------------------------------------------------

        stored_password = user.get(
            "password",
            ""
        )


        if not check_password_hash(
            stored_password,
            password
        ):

            return jsonify({

                "success": False,

                "message": "Invalid email or password."

            }), 401


        # ----------------------------------------------------
        # RETURN USER
        # ----------------------------------------------------

        return jsonify({

            "success": True,

            "message": "Login successful.",

            "user": {

                "id": str(user["_id"]),

                "name": user.get("name", ""),

                "email": user.get("email", ""),

                "role": user.get("role", ""),

                "contact": user.get("contact", ""),

                "address": user.get("address", ""),

                "latitude": user.get("latitude"),

                "longitude": user.get("longitude")
            }

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Login failed.",

            "error": str(e)

        }), 500


# ============================================================
# GET ALL USERS
# ============================================================

@app.route("/api/users", methods=["GET"])
def get_users():

    try:

        users = list(
            users_collection.find(
                {},
                {
                    "password": 0
                }
            ).sort(
                "createdAt",
                -1
            )
        )


        return jsonify({

            "success": True,

            "count": len(users),

            "users": serialize_documents(users)

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch users.",

            "error": str(e)

        }), 500


# ============================================================
# GET SINGLE USER
# ============================================================

@app.route("/api/users/<user_id>", methods=["GET"])
def get_single_user(user_id):

    try:

        if not valid_object_id(user_id):

            return jsonify({

                "success": False,

                "message": "Invalid user ID."

            }), 400


        user = users_collection.find_one({

            "_id": ObjectId(user_id)

        })


        if not user:

            return jsonify({

                "success": False,

                "message": "User not found."

            }), 404


        user.pop("password", None)


        return jsonify({

            "success": True,

            "user": serialize_document(user)

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch user.",

            "error": str(e)

        }), 500


# ============================================================
# DELETE USER
# ============================================================

@app.route("/api/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):

    try:

        if not valid_object_id(user_id):

            return jsonify({

                "success": False,

                "message": "Invalid user ID."

            }), 400


        result = users_collection.delete_one({

            "_id": ObjectId(user_id)

        })


        if result.deleted_count == 0:

            return jsonify({

                "success": False,

                "message": "User not found."

            }), 404


        return jsonify({

            "success": True,

            "message": "User deleted successfully."

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to delete user.",

            "error": str(e)

        }), 500


# ============================================================
# GET ALL DONATIONS
# ============================================================

@app.route("/api/donations", methods=["GET"])
def get_donations():

    try:

        donations = list(
            donations_collection.find({}).sort(
                "createdAt",
                -1
            )
        )


        return jsonify({

            "success": True,

            "count": len(donations),

            "donations": serialize_documents(
                donations
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch donations.",

            "error": str(e)

        }), 500


# ============================================================
# GET SINGLE DONATION
# ============================================================

@app.route("/api/donations/<donation_id>", methods=["GET"])
def get_single_donation(donation_id):

    try:

        if not valid_object_id(donation_id):

            return jsonify({

                "success": False,

                "message": "Invalid donation ID."

            }), 400


        donation = donations_collection.find_one({

            "_id": ObjectId(donation_id)

        })


        if not donation:

            return jsonify({

                "success": False,

                "message": "Donation not found."

            }), 404


        return jsonify({

            "success": True,

            "donation": serialize_document(
                donation
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch donation.",

            "error": str(e)

        }), 500


# ============================================================
# ADD FOOD DONATION
# ============================================================

@app.route("/api/donations", methods=["POST"])
def add_donation():

    try:

        data = request.get_json(silent=True) or {}


        food_name = str(
            data.get("foodName", "")
        ).strip()

        category = str(
            data.get("category", "")
        ).strip()

        quantity = data.get(
            "quantity",
            0
        )

        unit = str(
            data.get("unit", "kg")
        ).strip()

        meals = data.get(
            "meals",
            0
        )

        donor_id = data.get(
            "donorId"
        )

        donor_name = str(
            data.get(
                "donorName",
                "Donor"
            )
        ).strip()

        donor_email = str(
            data.get(
                "donorEmail",
                ""
            )
        ).strip()

        pickup_address = str(
            data.get(
                "pickupAddress",
                ""
            )
        ).strip()

        contact = str(
            data.get(
                "contact",
                ""
            )
        ).strip()

        prepared_date = str(
            data.get(
                "preparedDate",
                ""
            )
        ).strip()

        expiry_date = str(
            data.get(
                "expiryDate",
                ""
            )
        ).strip()

        description = str(
            data.get(
                "description",
                ""
            )
        ).strip()


        if not food_name:

            return jsonify({

                "success": False,

                "message": "Food name is required."

            }), 400


        if not donor_id:

            return jsonify({

                "success": False,

                "message": "Donor ID is required."

            }), 400


        donation = {

            "foodName": food_name,

            "category": category,

            "quantity": quantity,

            "unit": unit,

            "meals": meals,

            "preparedDate": prepared_date,

            "expiryDate": expiry_date,

            "pickupAddress": pickup_address,

            "contact": contact,

            "description": description,

            "donorId": donor_id,

            "donorName": donor_name,

            "donorEmail": donor_email,

            "status": "Available",

            "createdAt": current_time()
        }


        result = donations_collection.insert_one(
            donation
        )


        donation["id"] = str(
            result.inserted_id
        )

        # PyMongo adds _id to the inserted dictionary.
        # Remove the ObjectId before sending JSON response.
        donation.pop("_id", None)


        return jsonify({

            "success": True,

            "message": "Food donation added successfully.",

            "donation": donation

        }), 201


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to add donation.",

            "error": str(e)

        }), 500


# ============================================================
# UPDATE DONATION STATUS
# ============================================================

@app.route(
    "/api/donations/<donation_id>",
    methods=["PUT"]
)
def update_donation(donation_id):

    try:

        if not valid_object_id(donation_id):

            return jsonify({

                "success": False,

                "message": "Invalid donation ID."

            }), 400


        data = request.get_json(
            silent=True
        ) or {}


        allowed_fields = [

            "foodName",

            "category",

            "quantity",

            "unit",

            "meals",

            "preparedDate",

            "expiryDate",

            "pickupAddress",

            "contact",

            "description",

            "status"

        ]


        update_data = {}


        for field in allowed_fields:

            if field in data:

                update_data[field] = data[field]


        update_data["updatedAt"] = current_time()


        result = donations_collection.update_one(

            {
                "_id": ObjectId(donation_id)
            },

            {
                "$set": update_data
            }

        )


        if result.matched_count == 0:

            return jsonify({

                "success": False,

                "message": "Donation not found."

            }), 404


        updated = donations_collection.find_one({

            "_id": ObjectId(donation_id)

        })


        return jsonify({

            "success": True,

            "message": "Donation updated successfully.",

            "donation": serialize_document(
                updated
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to update donation.",

            "error": str(e)

        }), 500


# ============================================================
# DELETE DONATION
# ============================================================

@app.route(
    "/api/donations/<donation_id>",
    methods=["DELETE"]
)
def delete_donation(donation_id):

    try:

        if not valid_object_id(donation_id):

            return jsonify({

                "success": False,

                "message": "Invalid donation ID."

            }), 400


        result = donations_collection.delete_one({

            "_id": ObjectId(donation_id)

        })


        if result.deleted_count == 0:

            return jsonify({

                "success": False,

                "message": "Donation not found."

            }), 404


        return jsonify({

            "success": True,

            "message": "Donation deleted successfully."

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to delete donation.",

            "error": str(e)

        }), 500


# ============================================================
# CREATE FOOD REQUEST
# ============================================================

@app.route("/api/food-requests", methods=["POST"])
def create_food_request():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        food_id = data.get(
            "foodId"
        )

        ngo_id = data.get(
            "ngoId"
        )

        if not food_id or not ngo_id:

            return jsonify({

                "success": False,

                "message": "Food ID and NGO ID are required."

            }), 400


        # ----------------------------------------------------
        # CHECK DONATION
        # ----------------------------------------------------

        donation = None


        if valid_object_id(
            str(food_id)
        ):

            donation = donations_collection.find_one({

                "_id": ObjectId(food_id)

            })


        if not donation:

            return jsonify({

                "success": False,

                "message": "Food donation not found."

            }), 404


        # ----------------------------------------------------
        # CHECK ALREADY REQUESTED
        # ----------------------------------------------------

        existing_request = requests_collection.find_one({

            "foodId": food_id,

            "ngoId": ngo_id,

            "status": {
                "$nin": [
                    "Cancelled",
                    "Rejected"
                ]
            }

        })


        if existing_request:

            return jsonify({

                "success": False,

                "message": "This food has already been requested by this NGO."

            }), 409


        # ----------------------------------------------------
        # CREATE REQUEST
        # ----------------------------------------------------

        food_request = {

            "foodId": food_id,

            "foodName": data.get(
                "foodName",
                donation.get("foodName", "")
            ),

            "category": data.get(
                "category",
                donation.get("category", "")
            ),

            "quantity": data.get(
                "quantity",
                donation.get("quantity", 0)
            ),

            "unit": data.get(
                "unit",
                donation.get("unit", "kg")
            ),

            "meals": data.get(
                "meals",
                donation.get("meals", 0)
            ),

            "donorId": data.get(
                "donorId",
                donation.get("donorId")
            ),

            "donorName": data.get(
                "donorName",
                donation.get("donorName", "")
            ),

            "donorContact": data.get(
                "donorContact",
                donation.get("contact", "")
            ),

            "ngoId": ngo_id,

            "ngoName": data.get(
                "ngoName",
                "NGO"
            ),

            "pickupAddress": data.get(
                "pickupAddress",
                donation.get("pickupAddress", "")
            ),

            "status": "Pending",

            "requestedAt": current_time()
        }


        result = requests_collection.insert_one(
            food_request
        )


        # ----------------------------------------------------
        # UPDATE DONATION
        # ----------------------------------------------------

        if valid_object_id(
            str(food_id)
        ):

            donations_collection.update_one(

                {
                    "_id": ObjectId(food_id)
                },

                {
                    "$set": {
                        "status": "Requested",
                        "updatedAt": current_time()
                    }
                }

            )


        food_request["id"] = str(
            result.inserted_id
        )

        # PyMongo adds _id to the inserted dictionary.
        # Remove the ObjectId before sending JSON response.
        food_request.pop("_id", None)


        return jsonify({

            "success": True,

            "message": "Food request created successfully.",

            "request": food_request

        }), 201


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to create food request.",

            "error": str(e)

        }), 500


# ============================================================
# GET FOOD REQUESTS
# ============================================================

@app.route("/api/food-requests", methods=["GET"])
def get_food_requests():

    try:

        requests_list = list(
            requests_collection.find({}).sort(
                "requestedAt",
                -1
            )
        )


        return jsonify({

            "success": True,

            "count": len(requests_list),

            "requests": serialize_documents(
                requests_list
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch food requests.",

            "error": str(e)

        }), 500


# ============================================================
# GET NGO REQUESTS
# ============================================================

@app.route(
    "/api/food-requests/ngo/<ngo_id>",
    methods=["GET"]
)
def get_ngo_requests(ngo_id):

    try:

        requests_list = list(
            requests_collection.find({

                "ngoId": ngo_id

            }).sort(
                "requestedAt",
                -1
            )
        )


        return jsonify({

            "success": True,

            "count": len(requests_list),

            "requests": serialize_documents(
                requests_list
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch NGO requests.",

            "error": str(e)

        }), 500


# ============================================================
# UPDATE FOOD REQUEST
# ============================================================

@app.route(
    "/api/food-requests/<request_id>",
    methods=["PUT"]
)
def update_food_request(request_id):

    try:

        if not valid_object_id(request_id):

            return jsonify({

                "success": False,

                "message": "Invalid request ID."

            }), 400


        data = request.get_json(
            silent=True
        ) or {}


        allowed_fields = [

            "status",

            "volunteerId",

            "volunteerName",

            "assignedAt",

            "pickupStartedAt",

            "deliveredAt"

        ]


        update_data = {}


        for field in allowed_fields:

            if field in data:

                update_data[field] = data[field]


        update_data["updatedAt"] = current_time()


        result = requests_collection.update_one(

            {
                "_id": ObjectId(request_id)
            },

            {
                "$set": update_data
            }

        )


        if result.matched_count == 0:

            return jsonify({

                "success": False,

                "message": "Food request not found."

            }), 404


        updated_request = requests_collection.find_one({

            "_id": ObjectId(request_id)

        })


        # ----------------------------------------------------
        # IF DELIVERED, UPDATE DONATION
        # ----------------------------------------------------

        if data.get("status") == "Delivered":

            food_id = updated_request.get(
                "foodId"
            )


            if food_id and valid_object_id(
                str(food_id)
            ):

                donations_collection.update_one(

                    {
                        "_id": ObjectId(food_id)
                    },

                    {
                        "$set": {
                            "status": "Delivered",
                            "updatedAt": current_time()
                        }
                    }

                )


        return jsonify({

            "success": True,

            "message": "Food request updated successfully.",

            "request": serialize_document(
                updated_request
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to update food request.",

            "error": str(e)

        }), 500


# ============================================================
# CANCEL FOOD REQUEST
# ============================================================

@app.route(
    "/api/food-requests/<request_id>",
    methods=["DELETE"]
)
def cancel_food_request(request_id):

    try:

        if not valid_object_id(request_id):

            return jsonify({

                "success": False,

                "message": "Invalid request ID."

            }), 400


        request_document = requests_collection.find_one({

            "_id": ObjectId(request_id)

        })


        if not request_document:

            return jsonify({

                "success": False,

                "message": "Food request not found."

            }), 404


        requests_collection.update_one(

            {
                "_id": ObjectId(request_id)
            },

            {
                "$set": {
                    "status": "Cancelled",
                    "updatedAt": current_time()
                }
            }

        )


        return jsonify({

            "success": True,

            "message": "Food request cancelled successfully."

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to cancel request.",

            "error": str(e)

        }), 500


# ============================================================
# GET AVAILABLE FOOD
# ============================================================

@app.route(
    "/api/available-food",
    methods=["GET"]
)
def get_available_food():

    try:

        foods = list(
            donations_collection.find({

                "status": "Available"

            }).sort(
                "createdAt",
                -1
            )
        )


        return jsonify({

            "success": True,

            "count": len(foods),

            "foods": serialize_documents(
                foods
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch available food.",

            "error": str(e)

        }), 500


# ============================================================
# GET NGOs
# ============================================================

@app.route("/api/ngos", methods=["GET"])
def get_ngos():

    try:

        ngos = list(

            users_collection.find(

                {
                    "role": "ngo"
                },

                {
                    "password": 0
                }

            ).sort(
                "createdAt",
                -1
            )

        )


        return jsonify({

            "success": True,

            "count": len(ngos),

            "ngos": serialize_documents(
                ngos
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch NGOs.",

            "error": str(e)

        }), 500


# ============================================================
# GET VOLUNTEER TASKS
# ============================================================

@app.route(
    "/api/volunteer/tasks",
    methods=["GET"]
)
def get_volunteer_tasks():

    try:

        tasks = list(
            requests_collection.find({

                "status": {
                    "$in": [
                        "Approved",
                        "Pickup in Progress"
                    ]
                }

            }).sort(
                "requestedAt",
                -1
            )
        )


        return jsonify({

            "success": True,

            "count": len(tasks),

            "tasks": serialize_documents(
                tasks
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch volunteer tasks.",

            "error": str(e)

        }), 500


# ============================================================
# ACCEPT VOLUNTEER TASK
# ============================================================

@app.route(
    "/api/volunteer/tasks/<task_id>/accept",
    methods=["PUT"]
)
def accept_volunteer_task(task_id):

    try:

        if not valid_object_id(task_id):

            return jsonify({

                "success": False,

                "message": "Invalid task ID."

            }), 400


        data = request.get_json(
            silent=True
        ) or {}


        volunteer_id = data.get(
            "volunteerId"
        )

        volunteer_name = data.get(
            "volunteerName",
            "Volunteer"
        )


        if not volunteer_id:

            return jsonify({

                "success": False,

                "message": "Volunteer ID is required."

            }), 400


        task = requests_collection.find_one({

            "_id": ObjectId(task_id)

        })


        if not task:

            return jsonify({

                "success": False,

                "message": "Task not found."

            }), 404


        if task.get("volunteerId"):

            return jsonify({

                "success": False,

                "message": "This task is already assigned."

            }), 409


        result = requests_collection.update_one(

            {
                "_id": ObjectId(task_id),

                "volunteerId": {
                    "$exists": False
                }
            },

            {
                "$set": {

                    "volunteerId": volunteer_id,

                    "volunteerName": volunteer_name,

                    "assignedAt": current_time(),

                    "status": "Approved"

                }

            }

        )


        if result.modified_count == 0:

            return jsonify({

                "success": False,

                "message": "Task could not be assigned."

            }), 409


        updated = requests_collection.find_one({

            "_id": ObjectId(task_id)

        })


        return jsonify({

            "success": True,

            "message": "Pickup task accepted.",

            "task": serialize_document(
                updated
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to accept task.",

            "error": str(e)

        }), 500


# ============================================================
# START PICKUP
# ============================================================

@app.route(
    "/api/volunteer/tasks/<task_id>/start",
    methods=["PUT"]
)
def start_pickup(task_id):

    try:

        if not valid_object_id(task_id):

            return jsonify({

                "success": False,

                "message": "Invalid task ID."

            }), 400


        result = requests_collection.update_one(

            {
                "_id": ObjectId(task_id)
            },

            {
                "$set": {

                    "status": "Pickup in Progress",

                    "pickupStartedAt": current_time(),

                    "updatedAt": current_time()

                }

            }

        )


        if result.matched_count == 0:

            return jsonify({

                "success": False,

                "message": "Task not found."

            }), 404


        updated = requests_collection.find_one({

            "_id": ObjectId(task_id)

        })


        return jsonify({

            "success": True,

            "message": "Pickup started.",

            "task": serialize_document(
                updated
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to start pickup.",

            "error": str(e)

        }), 500


# ============================================================
# COMPLETE DELIVERY
# ============================================================

@app.route(
    "/api/volunteer/tasks/<task_id>/complete",
    methods=["PUT"]
)
def complete_delivery(task_id):

    try:

        if not valid_object_id(task_id):

            return jsonify({

                "success": False,

                "message": "Invalid task ID."

            }), 400


        result = requests_collection.update_one(

            {
                "_id": ObjectId(task_id)
            },

            {
                "$set": {

                    "status": "Delivered",

                    "deliveredAt": current_time(),

                    "updatedAt": current_time()

                }

            }

        )


        if result.matched_count == 0:

            return jsonify({

                "success": False,

                "message": "Task not found."

            }), 404


        updated = requests_collection.find_one({

            "_id": ObjectId(task_id)

        })


        # ----------------------------------------------------
        # UPDATE RELATED DONATION
        # ----------------------------------------------------

        food_id = updated.get(
            "foodId"
        )


        if food_id and valid_object_id(
            str(food_id)
        ):

            donations_collection.update_one(

                {
                    "_id": ObjectId(food_id)
                },

                {
                    "$set": {

                        "status": "Delivered",

                        "updatedAt": current_time()

                    }

                }

            )


        return jsonify({

            "success": True,

            "message": "Delivery completed successfully.",

            "task": serialize_document(
                updated
            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to complete delivery.",

            "error": str(e)

        }), 500


# ============================================================
# ADMIN DASHBOARD STATS
# ============================================================

@app.route(
    "/api/admin/stats",
    methods=["GET"]
)
def admin_stats():

    try:

        total_users = users_collection.count_documents({})

        total_donations = donations_collection.count_documents({})

        available_donations = donations_collection.count_documents({

            "status": "Available"

        })

        total_requests = requests_collection.count_documents({})

        delivered_requests = requests_collection.count_documents({

            "status": "Delivered"

        })

        total_ngos = users_collection.count_documents({

            "role": "ngo"

        })

        total_donors = users_collection.count_documents({

            "role": "donor"

        })

        total_volunteers = users_collection.count_documents({

            "role": "volunteer"

        })


        return jsonify({

            "success": True,

            "stats": {

                "totalUsers": total_users,

                "totalDonations": total_donations,

                "availableDonations": available_donations,

                "totalRequests": total_requests,

                "deliveredRequests": delivered_requests,

                "totalNGOs": total_ngos,

                "totalDonors": total_donors,

                "totalVolunteers": total_volunteers

            }

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Failed to fetch admin statistics.",

            "error": str(e)

        }), 500


# ============================================================
# SEARCH
# ============================================================

@app.route(
    "/api/search",
    methods=["GET"]
)
def search():

    try:

        query = request.args.get(
            "q",
            ""
        ).strip().lower()

        category = request.args.get(
            "category",
            "all"
        ).strip().lower()


        if not query:

            return jsonify({

                "success": True,

                "query": "",

                "category": category,

                "foods": [],

                "ngos": [],

                "donations": []

            })


        result = {

            "foods": [],

            "ngos": [],

            "donations": []

        }


        # ----------------------------------------------------
        # FOOD / DONATIONS
        # ----------------------------------------------------

        if category in [
            "all",
            "food",
            "donation"
        ]:

            donations = list(

                donations_collection.find({

                    "$or": [

                        {
                            "foodName": {
                                "$regex": query,
                                "$options": "i"
                            }
                        },

                        {
                            "category": {
                                "$regex": query,
                                "$options": "i"
                            }
                        },

                        {
                            "description": {
                                "$regex": query,
                                "$options": "i"
                            }
                        }

                    ]

                }).sort(
                    "createdAt",
                    -1
                )

            )


            if category in [
                "all",
                "food"
            ]:

                result["foods"] = serialize_documents(
                    donations
                )


            if category in [
                "all",
                "donation"
            ]:

                result["donations"] = serialize_documents(
                    donations
                )


        # ----------------------------------------------------
        # NGO SEARCH
        # ----------------------------------------------------

        if category in [
            "all",
            "ngo"
        ]:

            ngos = list(

                users_collection.find(

                    {

                        "role": "ngo",

                        "$or": [

                            {
                                "name": {
                                    "$regex": query,
                                    "$options": "i"
                                }
                            },

                            {
                                "email": {
                                    "$regex": query,
                                    "$options": "i"
                                }
                            },

                            {
                                "address": {
                                    "$regex": query,
                                    "$options": "i"
                                }
                            }

                        ]

                    },

                    {
                        "password": 0
                    }

                )

            )


            result["ngos"] = serialize_documents(
                ngos
            )


        return jsonify({

            "success": True,

            "query": query,

            "category": category,

            "foods": result["foods"],

            "ngos": result["ngos"],

            "donations": result["donations"],

            "totalResults": (

                len(result["foods"])

                + len(result["ngos"])

                + len(result["donations"])

            )

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "message": "Search failed.",

            "error": str(e)

        }), 500


# ============================================================
# ERROR HANDLER
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({

        "success": False,

        "message": "API endpoint not found."

    }), 404


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":

    try:

        client.admin.command("ping", maxTimeMS=5000)

        print("✅ MongoDB connected successfully!")

        print(f"✅ Database: {DB_NAME}")

    except Exception as e:

        print("❌ MongoDB connection failed!")

        print(f"ERROR: {e}")


    print("🚀 Starting ApnaKhana Flask Backend...")

    print("🌐 http://127.0.0.1:5000")

    print("🔍 DB Test: http://127.0.0.1:5000/api/db-test")


    app.run(

        host="127.0.0.1",

        port=5000,

        debug=True,

        use_reloader=False

    )